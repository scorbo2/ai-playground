extends Node3D

const ShipControllerScript = preload("res://scripts/ship_controller.gd")
const AsteroidScript = preload("res://scripts/asteroid.gd")
const ProjectileScript = preload("res://scripts/projectile.gd")
const HUDScript = preload("res://scripts/hud.gd")
const SynthAudioScript = preload("res://scripts/synth_audio.gd")
const DustFieldScript = preload("res://scripts/dust_field.gd")

const TARGET_ASTEROID_COUNT := 14
const PROJECTILE_SPEED := 78.0
const SHIP_COLLISION_RADIUS := 0.85
const RECYCLE_DISTANCE := 230.0

var _player
var _ship_scene: PackedScene
var _camera: Camera3D
var _hud
var _audio
var _dust
var _asteroid_root: Node3D
var _projectile_root: Node3D
var _effects_root: Node3D
var _asteroid_scenes: Array[PackedScene] = []
var _rock_material: ShaderMaterial
var _asteroids: Array = []
var _projectiles: Array = []
var _replacement_timers: Array[float] = []
var _rng := RandomNumberGenerator.new()
var _score := 0
var _destroyed := 0
var _game_over := false

func _ready() -> void:
	_rng.randomize()
	_configure_input()
	_load_assets()
	_build_environment()
	_build_roots()
	_build_player()
	_audio = SynthAudioScript.new()
	add_child(_audio)
	_hud = HUDScript.new()
	add_child(_hud)
	_hud.restart_requested.connect(_restart)
	_spawn_initial_field()
	_update_hud()

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("relaunch"):
		_restart()

func _physics_process(delta: float) -> void:
	if _game_over or _player == null:
		return
	_update_projectiles(delta)
	_check_ship_collision()
	if _game_over:
		return
	_update_replacements(delta)
	_recycle_distant_asteroids()

func _process(delta: float) -> void:
	if _player == null or _camera == null:
		return
	var camera_goal: Vector3 = _player.to_global(Vector3(0.0, 2.75, 9.4))
	var follow_weight := 1.0 - exp(-delta * 7.5)
	_camera.global_position = _camera.global_position.lerp(camera_goal, follow_weight)
	var look_goal: Vector3 = _player.to_global(Vector3(0.0, 0.30, -12.0))
	if _camera.global_position.distance_squared_to(look_goal) > 0.001:
		_camera.look_at(look_goal, _player.up())
	_camera.fov = lerpf(_camera.fov, 77.0 if _player.boosting else 68.0, 1.0 - exp(-delta * 4.0))
	_update_hud()

func _load_assets() -> void:
	var ship_scene: PackedScene = load("res://assets/models/skyjet.glb")
	if ship_scene == null:
		push_error("Skyjet GLB could not be loaded.")
		return
	_ship_scene = ship_scene
	for index in range(1, 7):
		var path := "res://assets/models/asteroid_%02d.glb" % index
		var scene: PackedScene = load(path)
		if scene == null:
			push_error("Missing asteroid asset: " + path)
		else:
			_asteroid_scenes.append(scene)
	_rock_material = ShaderMaterial.new()
	_rock_material.shader = load("res://shaders/rock_surface.gdshader")

func _build_roots() -> void:
	_asteroid_root = Node3D.new()
	_asteroid_root.name = "Asteroids"
	add_child(_asteroid_root)
	_projectile_root = Node3D.new()
	_projectile_root.name = "Projectiles"
	add_child(_projectile_root)
	_effects_root = Node3D.new()
	_effects_root.name = "Effects"
	add_child(_effects_root)

func _build_player() -> void:
	_player = ShipControllerScript.new()
	_player.name = "PlayerShip"
	_player.model_scene = _ship_scene
	add_child(_player)
	_player.fire_requested.connect(_spawn_projectile)

	_camera = Camera3D.new()
	_camera.name = "ChaseCamera"
	_camera.near = 0.08
	_camera.far = 1200.0
	_camera.fov = 68.0
	add_child(_camera)
	_camera.global_position = _player.to_global(Vector3(0.0, 2.75, 9.4))
	_camera.look_at(_player.to_global(Vector3(0.0, 0.3, -12.0)), _player.up())
	_camera.current = true
	_dust.target = _player

func _build_environment() -> void:
	var world := WorldEnvironment.new()
	world.name = "DeepSpaceEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = load("res://shaders/space_sky.gdshader")
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.32, 0.43, 0.64)
	environment.ambient_light_energy = 0.42
	environment.ambient_light_sky_contribution = 0.18
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.glow_enabled = true
	environment.glow_intensity = 0.72
	world.environment = environment
	add_child(world)

	var key_light := DirectionalLight3D.new()
	key_light.name = "DistantStarKey"
	key_light.rotation_degrees = Vector3(-38.0, -32.0, 0.0)
	key_light.light_color = Color(0.78, 0.86, 1.0)
	key_light.light_energy = 1.35
	key_light.shadow_enabled = true
	key_light.directional_shadow_max_distance = 145.0
	add_child(key_light)

	var rim_light := DirectionalLight3D.new()
	rim_light.name = "NebulaRim"
	rim_light.rotation_degrees = Vector3(28.0, 142.0, 12.0)
	rim_light.light_color = Color(0.26, 0.52, 1.0)
	rim_light.light_energy = 0.55
	add_child(rim_light)

	_dust = DustFieldScript.new()
	_dust.name = "LocalStarDust"
	add_child(_dust)

func _spawn_initial_field() -> void:
	var positions := [
		Vector3(-7.0, 1.0, -28.0),
		Vector3(8.0, -2.0, -36.0),
		Vector3(0.0, 0.0, -47.0),
		Vector3(-17.0, -5.0, -54.0),
		Vector3(18.0, 4.0, -62.0),
		Vector3(3.0, -8.0, -72.0),
		Vector3(-6.0, 3.0, -86.0),
		Vector3(24.0, -8.0, -98.0),
	]
	for point in positions:
		_spawn_asteroid(point)
	while _asteroids.size() < TARGET_ASTEROID_COUNT:
		_spawn_asteroid()

func _spawn_asteroid(spawn_position: Vector3 = Vector3.INF) -> void:
	if _asteroid_scenes.is_empty():
		return
	var asteroid = AsteroidScript.new()
	asteroid.model_scene = _asteroid_scenes[_rng.randi_range(0, _asteroid_scenes.size() - 1)]
	asteroid.surface_material = _rock_material
	asteroid.size = _rng.randf_range(1.25, 3.15)
	asteroid.velocity = Vector3(
		_rng.randf_range(-1.0, 1.0),
		_rng.randf_range(-1.0, 1.0),
		_rng.randf_range(-1.0, 1.0)
	) * _rng.randf_range(0.35, 1.35)
	asteroid.spin = Vector3(
		_rng.randf_range(-0.32, 0.32),
		_rng.randf_range(-0.32, 0.32),
		_rng.randf_range(-0.32, 0.32)
	)
	_asteroid_root.add_child(asteroid)
	asteroid.global_position = _random_spawn_position() if spawn_position == Vector3.INF else spawn_position
	asteroid.rotation = Vector3(_rng.randf() * TAU, _rng.randf() * TAU, _rng.randf() * TAU)
	_asteroids.append(asteroid)

func _random_spawn_position() -> Vector3:
	var distance := _rng.randf_range(62.0, 135.0)
	var lateral := _rng.randf_range(-65.0, 65.0)
	var vertical := _rng.randf_range(-46.0, 46.0)
	return _player.global_position + _player.forward() * distance + _player.right() * lateral + _player.up() * vertical

func _spawn_projectile(origin: Vector3, direction: Vector3) -> void:
	if _game_over:
		return
	var projectile = ProjectileScript.new()
	_projectile_root.add_child(projectile)
	projectile.global_position = origin
	projectile.velocity = direction * PROJECTILE_SPEED
	if direction.dot(_player.up()) < 0.999:
		projectile.look_at(origin + direction, _player.up())
	_projectiles.append(projectile)
	_audio.play_laser()

func _update_projectiles(delta: float) -> void:
	for projectile in _projectiles.duplicate():
		if not is_instance_valid(projectile):
			_projectiles.erase(projectile)
			continue
		var start: Vector3 = projectile.global_position
		var end: Vector3 = start + projectile.velocity * delta
		projectile.global_position = end
		projectile.lifetime -= delta
		var hit = null
		for asteroid in _asteroids:
			if not is_instance_valid(asteroid):
				continue
			var combined_radius: float = asteroid.collision_radius + 0.18
			if _distance_to_segment_squared(asteroid.global_position, start, end) <= combined_radius * combined_radius:
				hit = asteroid
				break
		if hit != null:
			_destroy_asteroid(hit)
			_remove_projectile(projectile)
		elif projectile.lifetime <= 0.0 or end.distance_squared_to(_player.global_position) > 225.0 * 225.0:
			_remove_projectile(projectile)

func _remove_projectile(projectile: Node) -> void:
	_projectiles.erase(projectile)
	projectile.queue_free()

func _destroy_asteroid(asteroid) -> void:
	if not _asteroids.has(asteroid):
		return
	var explosion_position: Vector3 = asteroid.global_position
	var explosion_size: float = asteroid.size
	_asteroids.erase(asteroid)
	asteroid.frozen = true
	asteroid.queue_free()
	_score += 100 + int(maxf(0.0, explosion_size - 1.0) * 45.0)
	_destroyed += 1
	_replacement_timers.append(_rng.randf_range(0.85, 1.65))
	_create_explosion(explosion_position, explosion_size)
	_audio.play_explosion()
	_update_hud()

func _check_ship_collision() -> void:
	for asteroid in _asteroids:
		if not is_instance_valid(asteroid):
			continue
		var combined_radius: float = asteroid.collision_radius + SHIP_COLLISION_RADIUS
		if _distance_to_segment_squared(asteroid.global_position, _player.previous_position, _player.global_position) <= combined_radius * combined_radius:
			_end_game()
			return

func _update_replacements(delta: float) -> void:
	for index in range(_replacement_timers.size() - 1, -1, -1):
		_replacement_timers[index] -= delta
		if _replacement_timers[index] <= 0.0:
			_replacement_timers.remove_at(index)
			_spawn_asteroid()

func _recycle_distant_asteroids() -> void:
	for asteroid in _asteroids:
		if is_instance_valid(asteroid) and asteroid.global_position.distance_squared_to(_player.global_position) > RECYCLE_DISTANCE * RECYCLE_DISTANCE:
			asteroid.global_position = _random_spawn_position()

func _end_game() -> void:
	if _game_over:
		return
	_game_over = true
	_player.controls_enabled = false
	_player.boosting = false
	for asteroid in _asteroids:
		asteroid.frozen = true
	for projectile in _projectiles:
		if is_instance_valid(projectile):
			projectile.queue_free()
	_projectiles.clear()
	_create_explosion(_player.global_position, 2.1)
	_audio.play_explosion()
	_hud.show_game_over(_score, _destroyed)

func _create_explosion(at_position: Vector3, radius: float) -> void:
	var effect := Node3D.new()
	_effects_root.add_child(effect)
	effect.global_position = at_position

	var debris_material := StandardMaterial3D.new()
	debris_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	debris_material.albedo_color = Color(1.0, 0.28, 0.07)
	debris_material.emission_enabled = true
	debris_material.emission = Color(1.0, 0.12, 0.025)
	debris_material.emission_energy_multiplier = 1.4
	var debris_mesh := BoxMesh.new()
	debris_mesh.size = Vector3(0.11, 0.08, 0.15)
	debris_mesh.material = debris_material

	var particles := CPUParticles3D.new()
	particles.amount = 42
	particles.lifetime = 0.85
	particles.one_shot = true
	particles.explosiveness = 1.0
	particles.spread = 180.0
	particles.gravity = Vector3.ZERO
	particles.initial_velocity_min = 3.0 + radius
	particles.initial_velocity_max = 7.0 + radius * 1.8
	particles.scale_amount_min = 0.65
	particles.scale_amount_max = 1.8
	particles.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
	particles.emission_sphere_radius = radius * 0.35
	particles.mesh = debris_mesh
	effect.add_child(particles)
	particles.finished.connect(effect.queue_free)
	particles.emitting = true

	var flash := OmniLight3D.new()
	flash.light_color = Color(1.0, 0.25, 0.06)
	flash.light_energy = 2.4
	flash.omni_range = 5.0 + radius * 3.0
	effect.add_child(flash)
	var tween := create_tween()
	tween.tween_property(flash, "light_energy", 0.0, 0.45)

func _update_hud() -> void:
	if _hud == null or _player == null:
		return
	var nearest := 999.0
	for asteroid in _asteroids:
		if is_instance_valid(asteroid):
			nearest = minf(nearest, _player.global_position.distance_to(asteroid.global_position) - asteroid.collision_radius)
	_hud.update_metrics(_score, _destroyed, _player.speed, _asteroids.size(), nearest, _player.boosting)

func _restart() -> void:
	get_tree().reload_current_scene()

func _configure_input() -> void:
	var bindings := {
		"pitch_up": [KEY_W, KEY_UP],
		"pitch_down": [KEY_S, KEY_DOWN],
		"yaw_left": [KEY_A, KEY_LEFT],
		"yaw_right": [KEY_D, KEY_RIGHT],
		"roll_left": [KEY_Q],
		"roll_right": [KEY_E],
		"boost": [KEY_SHIFT],
		"fire": [KEY_SPACE],
		"relaunch": [KEY_R, KEY_ENTER],
	}
	for action in bindings:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		for key in bindings[action]:
			var event := InputEventKey.new()
			event.physical_keycode = key
			InputMap.action_add_event(action, event)

func _distance_to_segment_squared(point: Vector3, start: Vector3, end: Vector3) -> float:
	var segment := end - start
	var length_squared := segment.length_squared()
	if length_squared < 0.000001:
		return point.distance_squared_to(start)
	var t := clampf((point - start).dot(segment) / length_squared, 0.0, 1.0)
	return point.distance_squared_to(start + segment * t)
