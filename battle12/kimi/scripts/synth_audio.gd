extends Node

const SAMPLE_RATE := 22050

var _laser: AudioStreamWAV
var _explosion: AudioStreamWAV

func _ready() -> void:
	_laser = _synthesize_laser()
	_explosion = _synthesize_explosion()

func play_laser() -> void:
	_play(_laser, -17.0, randf_range(0.96, 1.04))

func play_explosion() -> void:
	_play(_explosion, -8.0, randf_range(0.82, 1.12))

func _play(stream: AudioStreamWAV, volume: float, pitch: float) -> void:
	if stream == null:
		return
	var player := AudioStreamPlayer.new()
	player.stream = stream
	player.volume_db = volume
	player.pitch_scale = pitch
	add_child(player)
	player.finished.connect(player.queue_free)
	player.play()

func _synthesize_laser() -> AudioStreamWAV:
	var duration := 0.16
	var frame_count := int(SAMPLE_RATE * duration)
	var samples := PackedByteArray()
	samples.resize(frame_count * 2)
	var phase := 0.0
	for frame in range(frame_count):
		var t := float(frame) / SAMPLE_RATE
		var progress := t / duration
		var frequency := lerpf(1050.0, 180.0, progress)
		phase += TAU * frequency / SAMPLE_RATE
		var envelope := pow(1.0 - progress, 2.0) * minf(1.0, t * 500.0)
		var value := (sin(phase) * 0.65 + sin(phase * 2.03) * 0.20) * envelope * 0.65
		samples.encode_s16(frame * 2, int(clampf(value, -1.0, 1.0) * 32767.0))
	return _make_wav(samples)

func _synthesize_explosion() -> AudioStreamWAV:
	var duration := 0.72
	var frame_count := int(SAMPLE_RATE * duration)
	var samples := PackedByteArray()
	samples.resize(frame_count * 2)
	var filtered_noise := 0.0
	for frame in range(frame_count):
		var t := float(frame) / SAMPLE_RATE
		var progress := t / duration
		filtered_noise = lerpf(filtered_noise, randf_range(-1.0, 1.0), 0.20)
		var envelope := exp(-progress * 5.2) * minf(1.0, t * 150.0)
		var rumble := sin(TAU * (58.0 - progress * 24.0) * t) * 0.42
		var value := (filtered_noise * 1.25 + rumble) * envelope
		samples.encode_s16(frame * 2, int(clampf(value, -1.0, 1.0) * 32767.0))
	return _make_wav(samples)

func _make_wav(samples: PackedByteArray) -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = SAMPLE_RATE
	stream.stereo = false
	stream.data = samples
	return stream
