import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SmartHomeApp());
}

class Topics {
  static const sensors = 'smarthome/sensors';
  static const status = 'smarthome/status';
  static const alerts = 'smarthome/alerts';
  static const face = 'smarthome/face';
  static const faceEvents = 'smarthome/face/events';
  static const cameraBackend = 'smarthome/camera/backend';
  static const fan1 = 'smarthome/cmd/fan1';
  static const fan2 = 'smarthome/cmd/fan2';
  static const pump = 'smarthome/cmd/pump';
  static const door = 'smarthome/cmd/door';
  static const camera = 'smarthome/cmd/camera';
  static const allOff = 'smarthome/cmd/all_off';
}

class AppSettings {
  AppSettings({
    required this.useAws,
    required this.localHost,
    required this.localPort,
    required this.awsEndpoint,
    required this.awsPort,
  });

  final bool useAws;
  final String localHost;
  final int localPort;
  final String awsEndpoint;
  final int awsPort;

  String get host => useAws ? awsEndpoint : localHost;
  int get port => useAws ? awsPort : localPort;

  AppSettings copyWith({
    bool? useAws,
    String? localHost,
    int? localPort,
    String? awsEndpoint,
    int? awsPort,
  }) {
    return AppSettings(
      useAws: useAws ?? this.useAws,
      localHost: localHost ?? this.localHost,
      localPort: localPort ?? this.localPort,
      awsEndpoint: awsEndpoint ?? this.awsEndpoint,
      awsPort: awsPort ?? this.awsPort,
    );
  }

  static Future<AppSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return AppSettings(
      useAws: prefs.getBool('useAws') ?? true,
      localHost: prefs.getString('localHost') ?? '10.121.24.30',
      localPort: prefs.getInt('localPort') ?? 1883,
      awsEndpoint:
          prefs.getString('awsEndpoint') ??
          'a184ggwa834ixr-ats.iot.eu-central-1.amazonaws.com',
      awsPort: prefs.getInt('awsPort') ?? 8883,
    );
  }

  Future<void> save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('useAws', useAws);
    await prefs.setString('localHost', localHost);
    await prefs.setInt('localPort', localPort);
    await prefs.setString('awsEndpoint', awsEndpoint);
    await prefs.setInt('awsPort', awsPort);
  }
}

class MqttService extends ChangeNotifier {
  MqttService(this.settings);

  AppSettings settings;
  MqttServerClient? _client;
  StreamSubscription? _updatesSub;
  String state = 'Disconnected';
  String error = '';

  Map<String, dynamic> status = {};
  Map<String, dynamic> sensors = {};
  Map<String, dynamic> camera = {};
  final List<Map<String, dynamic>> events = [];

  bool get connected =>
      _client?.connectionStatus?.state == MqttConnectionState.connected;

  Future<void> reconnect([AppSettings? next]) async {
    if (next != null) {
      settings = next;
      await settings.save();
    }
    disconnect();
    await connect();
  }

  Future<void> connect() async {
    state = 'Connecting';
    error = '';
    notifyListeners();

   final clientId = 'smarthome-phone-${DateTime.now().millisecondsSinceEpoch}';
    final client = MqttServerClient.withPort(
      settings.host,
      clientId,
      settings.port,
    );
    client.logging(on: false);
    client.keepAlivePeriod = 30;
    client.autoReconnect = true;
    client.resubscribeOnAutoReconnect = true;
    client.setProtocolV311();
    client.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .startClean()
        .withWillQos(MqttQos.atLeastOnce);
    client.onConnected = () {
      state = 'Connected';
      _subscribeAll();
      notifyListeners();
    };
    client.onDisconnected = () {
      state = 'Disconnected';
      notifyListeners();
    };
    client.onAutoReconnect = () {
      state = 'Reconnecting';
      notifyListeners();
    };
    client.onAutoReconnected = () {
      state = 'Connected';
      notifyListeners();
    };

    if (settings.useAws) {
      client.secure = true;
      client.securityContext = await _awsSecurityContext();
    }

    _client = client;

    try {
      await client.connect();
      _updatesSub = client.updates?.listen(_handleMessages);
      if (connected) {
        state = 'Connected';
        _subscribeAll();
      } else {
        state = 'Disconnected';
        error =
            client.connectionStatus?.returnCode?.name ?? 'MQTT connect failed';
        client.disconnect();
      }
    } catch (exc) {
      state = 'Disconnected';
      error = exc.toString();
      client.disconnect();
    }
    notifyListeners();
  }

  Future<SecurityContext> _awsSecurityContext() async {
    final root = await rootBundle.loadString('assets/certs/AmazonRootCA1.pem');
    final cert = await rootBundle.loadString(
      'assets/certs/device-certificate.pem.crt',
    );
    final key = await rootBundle.loadString('assets/certs/private.pem.key');
    final context = SecurityContext(withTrustedRoots: false);
    context.setTrustedCertificatesBytes(utf8.encode(root));
    context.useCertificateChainBytes(utf8.encode(cert));
    context.usePrivateKeyBytes(utf8.encode(key));
    return context;
  }

  void _subscribeAll() {
    final client = _client;
    if (client == null || !connected) return;
    for (final topic in [
      Topics.status,
      Topics.sensors,
      Topics.alerts,
      Topics.cameraBackend,
      Topics.face,
      Topics.faceEvents,
    ]) {
      client.subscribe(topic, MqttQos.atLeastOnce);
    }
  }

  void _handleMessages(List<MqttReceivedMessage<MqttMessage>> messages) {
    for (final message in messages) {
      final publish = message.payload as MqttPublishMessage;
      final payload = MqttPublishPayload.bytesToStringAsString(
        publish.payload.message,
      );
      final decoded = _decode(payload);

      switch (message.topic) {
        case Topics.status:
          status = decoded;
          break;
        case Topics.sensors:
          sensors = decoded;
          break;
        case Topics.cameraBackend:
          camera = decoded;
          break;
        case Topics.face:
        case Topics.faceEvents:
        case Topics.alerts:
          events.insert(0, {
            'topic': message.topic,
            'payload': decoded.isEmpty ? {'raw': payload} : decoded,
            'received_at': DateTime.now().toIso8601String(),
          });
          if (events.length > 80) {
            events.removeRange(80, events.length);
          }
          break;
      }
    }
    notifyListeners();
  }

  Map<String, dynamic> _decode(String payload) {
    try {
      final value = jsonDecode(payload);
      if (value is Map<String, dynamic>) return value;
      return {'value': value};
    } catch (_) {
      return {};
    }
  }

  void publish(String topic, String payload, {bool retain = false}) {
    final client = _client;
    if (client == null || !connected) {
      error = 'MQTT is not connected';
      notifyListeners();
      return;
    }
    final builder = MqttClientPayloadBuilder()..addString(payload);
    client.publishMessage(
      topic,
      MqttQos.atLeastOnce,
      builder.payload!,
      retain: retain,
    );
  }

  void requestCamera() => publish(Topics.camera, 'GET');
  void relay(String topic, bool on) => publish(topic, on ? 'ON' : 'OFF');
  void door(String command) => publish(Topics.door, command);
  void allOff() => publish(Topics.allOff, 'OFF');

  void disconnect() {
    _updatesSub?.cancel();
    _updatesSub = null;
    _client?.disconnect();
    _client = null;
    state = 'Disconnected';
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}

class SmartHomeApp extends StatefulWidget {
  const SmartHomeApp({super.key});

  @override
  State<SmartHomeApp> createState() => _SmartHomeAppState();
}

class _SmartHomeAppState extends State<SmartHomeApp> {
  MqttService? service;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    final settings = await AppSettings.load();
    final mqtt = MqttService(settings);
    setState(() => service = mqtt);
    await mqtt.connect();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Smart Home',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff14866d),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        cardTheme: const CardThemeData(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(8)),
          ),
        ),
      ),
      home: service == null
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : HomeScreen(service: service!),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.service});

  final MqttService service;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.service,
      builder: (context, _) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Smart Home'),
            actions: [
              IconButton(
                tooltip: 'Reconnect',
                icon: const Icon(Icons.refresh),
                onPressed: widget.service.reconnect,
              ),
              IconButton(
                tooltip: 'Settings',
                icon: const Icon(Icons.settings),
                onPressed: () => _openSettings(context),
              ),
            ],
          ),
          body: IndexedStack(
            index: tab,
            children: [
              Dashboard(service: widget.service),
              CameraPanel(service: widget.service),
              EventsPanel(service: widget.service),
            ],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: tab,
            onDestinationSelected: (value) => setState(() => tab = value),
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.dashboard_outlined),
                selectedIcon: Icon(Icons.dashboard),
                label: 'Home',
              ),
              NavigationDestination(
                icon: Icon(Icons.videocam_outlined),
                selectedIcon: Icon(Icons.videocam),
                label: 'Camera',
              ),
              NavigationDestination(
                icon: Icon(Icons.event_note_outlined),
                selectedIcon: Icon(Icons.event_note),
                label: 'Events',
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _openSettings(BuildContext context) async {
    final next = await showDialog<AppSettings>(
      context: context,
      builder: (_) => SettingsDialog(settings: widget.service.settings),
    );
    if (next != null) {
      await widget.service.reconnect(next);
    }
  }
}

class Dashboard extends StatelessWidget {
  const Dashboard({super.key, required this.service});

  final MqttService service;

  @override
  Widget build(BuildContext context) {
    final status = service.status;
    final sensors = service.sensors;
    return RefreshIndicator(
      onRefresh: service.reconnect,
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          ConnectionCard(service: service),
          const SizedBox(height: 12),
          GridView.count(
            shrinkWrap: true,
            crossAxisCount: MediaQuery.sizeOf(context).width > 560 ? 3 : 2,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            childAspectRatio: 1.45,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              SensorTile(
                'Gas',
                sensors['mq2'],
                sensors['gas_status'] ?? '-',
                Icons.local_fire_department,
              ),
              SensorTile(
                'Garden',
                sensors['garden_moisture_raw'],
                sensors['garden_status'] ?? '-',
                Icons.water_drop,
              ),
              SensorTile(
                'Leak',
                sensors['bathroom_leak_raw'],
                sensors['leak_status'] ?? '-',
                Icons.opacity,
              ),
              SensorTile('Temp', sensors['temp_c'], 'C', Icons.thermostat),
              SensorTile(
                'Humidity',
                sensors['humidity_pct'],
                '%',
                Icons.cloud_outlined,
              ),
              SensorTile(
                'PIC',
                status['pic_connected'] == true ? 'OK' : '-',
                service.connected ? 'MQTT' : '-',
                Icons.memory,
              ),
            ],
          ),
          const SizedBox(height: 12),
          RelayCard(
            title: 'Kitchen Fan',
            value: status['fan1'] == true || status['relay_fan1_on'] == true,
            icon: Icons.air,
            onChanged: (value) => service.relay(Topics.fan1, value),
          ),
          RelayCard(
            title: 'Room Fan',
            value: status['fan2'] == true || status['relay_fan2_on'] == true,
            icon: Icons.mode_fan_off_outlined,
            onChanged: (value) => service.relay(Topics.fan2, value),
          ),
          RelayCard(
            title: 'Pump',
            value: status['pump'] == true || status['relay_pump_on'] == true,
            icon: Icons.water,
            onChanged: (value) => service.relay(Topics.pump, value),
          ),
          DoorCard(service: service),
          FilledButton.icon(
            onPressed: service.allOff,
            icon: const Icon(Icons.power_settings_new),
            label: const Text('All Off'),
          ),
        ],
      ),
    );
  }
}

class ConnectionCard extends StatelessWidget {
  const ConnectionCard({super.key, required this.service});

  final MqttService service;

  @override
  Widget build(BuildContext context) {
    final color = service.connected ? Colors.green : Colors.red;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.circle, color: color, size: 14),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    service.state,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  Text(
                    '${service.settings.useAws ? 'AWS' : 'Local'}  ${service.settings.host}:${service.settings.port}',
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (service.error.isNotEmpty)
                    Text(
                      service.error,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.red),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SensorTile extends StatelessWidget {
  const SensorTile(this.title, this.value, this.unit, this.icon, {super.key});

  final String title;
  final Object? value;
  final Object? unit;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon),
            Text(title, style: Theme.of(context).textTheme.labelLarge),
            FittedBox(
              alignment: Alignment.centerLeft,
              fit: BoxFit.scaleDown,
              child: Text(
                '${value ?? '-'} ${unit ?? ''}',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class RelayCard extends StatelessWidget {
  const RelayCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    required this.onChanged,
  });

  final String title;
  final bool value;
  final IconData icon;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: SwitchListTile(
        secondary: Icon(icon),
        title: Text(title),
        subtitle: Text(value ? 'ON' : 'OFF'),
        value: value,
        onChanged: onChanged,
      ),
    );
  }
}

class DoorCard extends StatelessWidget {
  const DoorCard({super.key, required this.service});

  final MqttService service;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.door_front_door_outlined),
                const SizedBox(width: 10),
                Text('Door', style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.tonalIcon(
                  onPressed: () => service.door('GRANTED'),
                  icon: const Icon(Icons.lock_open),
                  label: const Text('Grant'),
                ),
                FilledButton.tonalIcon(
                  onPressed: () => service.door('DENIED'),
                  icon: const Icon(Icons.block),
                  label: const Text('Deny'),
                ),
                OutlinedButton.icon(
                  onPressed: () => service.door('CLOSE'),
                  icon: const Icon(Icons.lock),
                  label: const Text('Close'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class CameraPanel extends StatefulWidget {
  const CameraPanel({super.key, required this.service});

  final MqttService service;

  @override
  State<CameraPanel> createState() => _CameraPanelState();
}

class _CameraPanelState extends State<CameraPanel> {
  bool enrolling = false;
  bool loadingFaces = false;
  List<String> faces = [];

  String get videoUrl {
    final url = widget.service.camera['video_url'];
    if (url is String && url.isNotEmpty) return url;
    return 'http://${widget.service.settings.localHost}:5000/video';
  }

  String get enrollUrl {
    final url = widget.service.camera['enroll_url'];
    if (url is String && url.isNotEmpty) return url;
    return 'http://${widget.service.settings.localHost}:5000/enroll';
  }

  String get facesUrl {
    final url = widget.service.camera['faces_url'];
    if (url is String && url.isNotEmpty) return url;
    return 'http://${widget.service.settings.localHost}:5000/faces';
  }

  @override
  Widget build(BuildContext context) {
    final camera = widget.service.camera;
    final connected = camera['camera_connected'] == true;
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(connected ? Icons.videocam : Icons.videocam_off),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        connected ? 'Camera Online' : 'Camera Offline',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(videoUrl, overflow: TextOverflow.ellipsis),
                if (camera['last_error'] != null)
                  Text(
                    'Source: ${camera['camera_url'] ?? '-'}',
                    overflow: TextOverflow.ellipsis,
                  ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilledButton.icon(
                      onPressed: () {
                        widget.service.requestCamera();
                        Future.delayed(const Duration(milliseconds: 600), () {
                          if (mounted) _openVideo();
                        });
                      },
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('Open'),
                    ),
                    OutlinedButton.icon(
                      onPressed: widget.service.requestCamera,
                      icon: const Icon(Icons.sync),
                      label: const Text('Refresh'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        EnrollCard(enrolling: enrolling, onEnroll: _enroll),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'Faces',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const Spacer(),
                    IconButton(
                      tooltip: 'Reload',
                      onPressed: loadingFaces ? null : _loadFaces,
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
                if (faces.isEmpty) const Text('-'),
                for (final face in faces)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.person),
                    title: Text(face),
                    trailing: IconButton(
                      tooltip: 'Delete',
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => _deleteFace(face),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  void _openVideo() {
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => CameraWebView(url: videoUrl)));
  }

  Future<void> _enroll(String name) async {
    setState(() => enrolling = true);
    try {
      final request = http.MultipartRequest('POST', Uri.parse(enrollUrl));
      request.fields['name'] = name;
      final response = await request.send().timeout(
        const Duration(seconds: 12),
      );
      final body = await response.stream.bytesToString();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception(body);
      }
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Enrolled $name')));
      }
      await _loadFaces();
    } catch (exc) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Enroll failed: $exc')));
      }
    } finally {
      if (mounted) setState(() => enrolling = false);
    }
  }

  Future<void> _loadFaces() async {
    setState(() => loadingFaces = true);
    try {
      final response = await http
          .get(Uri.parse(facesUrl))
          .timeout(const Duration(seconds: 8));
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final raw = data['faces'];
      setState(() {
        faces = raw is List ? raw.map((e) => e.toString()).toList() : [];
      });
    } catch (exc) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Faces failed: $exc')));
      }
    } finally {
      if (mounted) setState(() => loadingFaces = false);
    }
  }

  Future<void> _deleteFace(String name) async {
    try {
      final encoded = Uri.encodeComponent(name);
      final response = await http
          .delete(Uri.parse('$facesUrl/$encoded'))
          .timeout(const Duration(seconds: 8));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception(response.body);
      }
      await _loadFaces();
    } catch (exc) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Delete failed: $exc')));
      }
    }
  }
}

class EnrollCard extends StatefulWidget {
  const EnrollCard({
    super.key,
    required this.enrolling,
    required this.onEnroll,
  });

  final bool enrolling;
  final ValueChanged<String> onEnroll;

  @override
  State<EnrollCard> createState() => _EnrollCardState();
}

class _EnrollCardState extends State<EnrollCard> {
  final controller = TextEditingController();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Enroll Face', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              textInputAction: TextInputAction.done,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                labelText: 'Name',
              ),
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: widget.enrolling ? null : _submit,
              icon: widget.enrolling
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.person_add),
              label: const Text('Enroll'),
            ),
          ],
        ),
      ),
    );
  }

  void _submit() {
    final name = controller.text.trim();
    if (name.isEmpty) return;
    widget.onEnroll(name);
  }
}

class CameraWebView extends StatefulWidget {
  const CameraWebView({super.key, required this.url});

  final String url;

  @override
  State<CameraWebView> createState() => _CameraWebViewState();
}

class _CameraWebViewState extends State<CameraWebView> {
  late final WebViewController controller;

  @override
  void initState() {
    super.initState();
    controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Camera'),
        actions: [
          IconButton(
            tooltip: 'Reload',
            onPressed: () => controller.reload(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: WebViewWidget(controller: controller),
    );
  }
}

class EventsPanel extends StatelessWidget {
  const EventsPanel({super.key, required this.service});

  final MqttService service;

  @override
  Widget build(BuildContext context) {
    final formatter = DateFormat('HH:mm:ss');
    return ListView.builder(
      padding: const EdgeInsets.all(14),
      itemCount: service.events.length,
      itemBuilder: (context, index) {
        final event = service.events[index];
        final payload = event['payload'] as Map<String, dynamic>? ?? {};
        final type = payload['type'] ?? payload['raw'] ?? event['topic'];
        final received = DateTime.tryParse(
          event['received_at']?.toString() ?? '',
        );
        return Card(
          child: ListTile(
            leading: Icon(_eventIcon(type.toString())),
            title: Text(type.toString()),
            subtitle: Text(_eventSubtitle(payload)),
            trailing: Text(received == null ? '' : formatter.format(received)),
          ),
        );
      },
    );
  }

  IconData _eventIcon(String type) {
    if (type.contains('recognized')) return Icons.verified_user;
    if (type.contains('unknown') || type.contains('denied')) {
      return Icons.warning;
    }
    if (type.contains('gas') || type.contains('leak')) {
      return Icons.priority_high;
    }
    return Icons.event;
  }

  String _eventSubtitle(Map<String, dynamic> payload) {
    final parts = <String>[];
    if (payload['name'] != null) parts.add(payload['name'].toString());
    if (payload['confidence'] != null) {
      parts.add('confidence ${payload['confidence']}');
    }
    if (payload['payload'] != null) parts.add(payload['payload'].toString());
    return parts.isEmpty ? jsonEncode(payload) : parts.join('  ');
  }
}

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key, required this.settings});

  final AppSettings settings;

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late bool useAws;
  late final TextEditingController localHost;
  late final TextEditingController localPort;
  late final TextEditingController awsEndpoint;
  late final TextEditingController awsPort;

  @override
  void initState() {
    super.initState();
    useAws = widget.settings.useAws;
    localHost = TextEditingController(text: widget.settings.localHost);
    localPort = TextEditingController(
      text: widget.settings.localPort.toString(),
    );
    awsEndpoint = TextEditingController(text: widget.settings.awsEndpoint);
    awsPort = TextEditingController(text: widget.settings.awsPort.toString());
  }

  @override
  void dispose() {
    localHost.dispose();
    localPort.dispose();
    awsEndpoint.dispose();
    awsPort.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('MQTT Settings'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('AWS IoT'),
              value: useAws,
              onChanged: (value) => setState(() => useAws = value),
            ),
            TextField(
              controller: localHost,
              decoration: const InputDecoration(labelText: 'Local host'),
            ),
            TextField(
              controller: localPort,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Local port'),
            ),
            TextField(
              controller: awsEndpoint,
              decoration: const InputDecoration(labelText: 'AWS endpoint'),
            ),
            TextField(
              controller: awsPort,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'AWS port'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.pop(
              context,
              widget.settings.copyWith(
                useAws: useAws,
                localHost: localHost.text.trim(),
                localPort: int.tryParse(localPort.text.trim()) ?? 1883,
                awsEndpoint: awsEndpoint.text.trim(),
                awsPort: int.tryParse(awsPort.text.trim()) ?? 8883,
              ),
            );
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
