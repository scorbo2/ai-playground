extends Node3D

const FIELD_SIZE := 110.0
const HALF_FIELD := FIELD_SIZE * 0.5
const PARTICLE_COUNT := 260

var target: Node3D
var _positions: Array[Vector3] = []
var _scales: Array[float] = []
var _multimesh: MultiMesh

func _ready() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7319
	var mesh := SphereMesh.new()
	mesh.radius = 0.032
	mesh.height = 0.064
	mesh.radial_segments = 4
	mesh.rings = 2
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.albedo_color = Color.WHITE

	_multimesh = MultiMesh.new()
	_multimesh.transform_format = MultiMesh.TRANSFORM_3D
	_multimesh.use_colors = true
	_multimesh.mesh = mesh
	_multimesh.instance_count = PARTICLE_COUNT
	var instance := MultiMeshInstance3D.new()
	instance.multimesh = _multimesh
	instance.material_override = material
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(instance)

	for index in range(PARTICLE_COUNT):
		var point := Vector3(
			rng.randf_range(-HALF_FIELD, HALF_FIELD),
			rng.randf_range(-HALF_FIELD, HALF_FIELD),
			rng.randf_range(-HALF_FIELD, HALF_FIELD)
		)
		_positions.append(point)
		_scales.append(rng.randf_range(0.45, 1.65))
		_multimesh.set_instance_transform(index, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * _scales[index]), point))
		var brightness := rng.randf_range(0.25, 0.75)
		_multimesh.set_instance_color(index, Color(brightness * 0.65, brightness * 0.85, brightness))

func _process(_delta: float) -> void:
	if target == null or _multimesh == null:
		return
	for index in range(PARTICLE_COUNT):
		var point := _positions[index]
		var difference := point - target.global_position
		var wrapped := false
		for axis in range(3):
			if difference[axis] > HALF_FIELD:
				point[axis] -= FIELD_SIZE
				wrapped = true
			elif difference[axis] < -HALF_FIELD:
				point[axis] += FIELD_SIZE
				wrapped = true
		if wrapped:
			_positions[index] = point
			_multimesh.set_instance_transform(index, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * _scales[index]), point))
