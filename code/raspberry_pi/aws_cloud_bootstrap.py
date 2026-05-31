#!/usr/bin/env python3
"""
Create/update the AWS cloud enhancement layer:

- IoT policy that allows stable unique Pi client IDs
- DynamoDB table for history
- Lambda writer for sensors/status/alerts/face/camera events
- IoT Rule that forwards smarthome/# MQTT messages into Lambda
- Optional SNS topic/email subscription for push-style alerts

Run this from a machine where AWS credentials are already configured:
    python3 aws_cloud_bootstrap.py --region eu-central-1 --cert-arn arn:aws:iot:...
"""

import argparse
import io
import json
import time
import zipfile

import boto3
from botocore.exceptions import ClientError


LAMBDA_CODE = r'''
import json
import os
import time
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
table = dynamodb.Table(os.environ["TABLE_NAME"])
sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return str(value)


def _notify_message(topic, event):
    typ = str(event.get("type", "")).lower()
    if "alerts" in topic:
        return f"Smart Home alert: {typ or 'alert'}"
    if typ in ("unknown_face", "face_recognized", "door_command", "face_denied"):
        return f"Smart Home event: {typ}"
    return ""


def handler(event, context):
    topic = str(event.get("topic", "smarthome/unknown"))
    ts = int(event.get("ts") or int(time.time() * 1000))
    payload = json.dumps(event, default=_json_default, separators=(",", ":"))

    table.put_item(Item={
        "pk": topic.replace("/", "#"),
        "sk": ts,
        "topic": topic,
        "payload": payload,
        "ttl": int(time.time()) + 60 * 60 * 24 * 90,
    })

    message = _notify_message(topic, event)
    if message and sns_topic_arn:
        sns.publish(
            TopicArn=sns_topic_arn,
            Subject="Smart Home",
            Message=message + "\n\n" + payload[:1200],
        )

    return {"ok": True, "topic": topic, "ts": ts}
'''


def ensure_table(dynamodb, table_name):
    try:
        table = dynamodb.describe_table(TableName=table_name)["Table"]
        print(f"OK table exists: {table_name} ({table['TableStatus']})")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    dynamodb.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "N"},
        ],
    )
    waiter = dynamodb.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    dynamodb.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )
    print(f"OK created table: {table_name}")


def ensure_lambda_role(iam, role_name, table_arn, sns_topic_arn):
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
        print(f"OK role exists: {role_name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
        )["Role"]
        print(f"OK created role: {role_name}")

    resources = [table_arn]
    if sns_topic_arn:
        resources.append(sns_topic_arn)

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["dynamodb:PutItem"],
                "Resource": table_arn,
            },
        ],
    }
    if sns_topic_arn:
        policy["Statement"].append({
            "Effect": "Allow",
            "Action": ["sns:Publish"],
            "Resource": sns_topic_arn,
        })

    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{role_name}-inline",
        PolicyDocument=json.dumps(policy),
    )

    time.sleep(8)
    return role["Arn"]


def zip_lambda_code():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lambda_function.py", LAMBDA_CODE)
    return buf.getvalue()


def ensure_lambda(lambda_client, fn_name, role_arn, table_name, sns_topic_arn):
    code = zip_lambda_code()
    env = {"TABLE_NAME": table_name}
    if sns_topic_arn:
        env["SNS_TOPIC_ARN"] = sns_topic_arn

    try:
        fn = lambda_client.get_function(FunctionName=fn_name)["Configuration"]
        lambda_client.update_function_code(FunctionName=fn_name, ZipFile=code, Publish=True)
        lambda_client.update_function_configuration(
            FunctionName=fn_name,
            Role=role_arn,
            Runtime="python3.12",
            Handler="lambda_function.handler",
            Timeout=10,
            Environment={"Variables": env},
        )
        print(f"OK updated lambda: {fn_name}")
        return fn["FunctionArn"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    fn = lambda_client.create_function(
        FunctionName=fn_name,
        Runtime="python3.12",
        Role=role_arn,
        Handler="lambda_function.handler",
        Code={"ZipFile": code},
        Timeout=10,
        Environment={"Variables": env},
        Publish=True,
    )["FunctionArn"]
    print(f"OK created lambda: {fn_name}")
    return fn


def ensure_iot_policy(iot, account_id, region, policy_name, cert_arn):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["iot:Connect"],
                "Resource": [
                    f"arn:aws:iot:{region}:{account_id}:client/smarthome-pi-*",
                    f"arn:aws:iot:{region}:{account_id}:client/smarthome-local-*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["iot:Publish", "iot:Receive", "iot:RetainPublish"],
                "Resource": f"arn:aws:iot:{region}:{account_id}:topic/smarthome/*",
            },
            {
                "Effect": "Allow",
                "Action": ["iot:Subscribe"],
                "Resource": f"arn:aws:iot:{region}:{account_id}:topicfilter/smarthome/*",
            },
        ],
    }

    doc = json.dumps(policy)
    try:
        iot.create_policy(policyName=policy_name, policyDocument=doc)
        print(f"OK created IoT policy: {policy_name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
        versions = iot.list_policy_versions(policyName=policy_name)["policyVersions"]
        non_default = [v for v in versions if not v["isDefaultVersion"]]
        if len(versions) >= 5 and non_default:
            iot.delete_policy_version(policyName=policy_name, policyVersionId=non_default[0]["versionId"])
        iot.create_policy_version(policyName=policy_name, policyDocument=doc, setAsDefault=True)
        print(f"OK updated IoT policy: {policy_name}")

    if cert_arn:
        try:
            iot.attach_policy(policyName=policy_name, target=cert_arn)
            print(f"OK attached IoT policy to cert: {cert_arn}")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise


def ensure_iot_rule(iot, lambda_client, rule_name, lambda_arn, account_id, region):
    sql = "SELECT *, topic() as topic, timestamp() as ts FROM 'smarthome/#'"
    iot.put_topic_rule(
        ruleName=rule_name,
        topicRulePayload={
            "sql": sql,
            "awsIotSqlVersion": "2016-03-23",
            "ruleDisabled": False,
            "actions": [{"lambda": {"functionArn": lambda_arn}}],
        },
    )
    rule_arn = f"arn:aws:iot:{region}:{account_id}:rule/{rule_name}"
    try:
        lambda_client.add_permission(
            FunctionName=lambda_arn,
            StatementId=f"{rule_name}-invoke",
            Action="lambda:InvokeFunction",
            Principal="iot.amazonaws.com",
            SourceArn=rule_arn,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
    print(f"OK IoT rule: {rule_name}")


def ensure_sns(sns, email):
    topic_arn = sns.create_topic(Name="SmartHomeAlerts")["TopicArn"]
    print(f"OK SNS topic: {topic_arn}")
    if email:
        sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=email)
        print(f"OK SNS email subscription requested: {email}")
        print("Check that email inbox and confirm the subscription.")
    return topic_arn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--table", default="SmartHomeEvents")
    parser.add_argument("--lambda-name", default="SmartHomeTelemetryWriter")
    parser.add_argument("--lambda-role", default="SmartHomeTelemetryWriterRole")
    parser.add_argument("--iot-rule", default="SmartHomeToHistory")
    parser.add_argument("--iot-policy", default="SmartHomePiPolicy")
    parser.add_argument("--cert-arn", default="", help="AWS IoT certificate ARN to attach policy to")
    parser.add_argument("--email", default="", help="Optional email subscription for SNS alerts")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]

    dynamodb = session.client("dynamodb")
    iam = session.client("iam")
    lambda_client = session.client("lambda")
    iot = session.client("iot")
    sns = session.client("sns")

    ensure_table(dynamodb, args.table)
    table_arn = dynamodb.describe_table(TableName=args.table)["Table"]["TableArn"]
    sns_topic_arn = ensure_sns(sns, args.email)
    role_arn = ensure_lambda_role(iam, args.lambda_role, table_arn, sns_topic_arn)
    lambda_arn = ensure_lambda(lambda_client, args.lambda_name, role_arn, args.table, sns_topic_arn)
    ensure_iot_rule(iot, lambda_client, args.iot_rule, lambda_arn, account_id, args.region)
    ensure_iot_policy(iot, account_id, args.region, args.iot_policy, args.cert_arn)

    print("")
    print("AWS cloud layer is ready.")
    print("Important: if you did not pass --cert-arn, attach the policy to the Pi certificate in AWS IoT Core.")


if __name__ == "__main__":
    main()
