extends Node3D

var velocity := Vector3.ZERO
var lifetime := 2.2

func _ready() -> void:
	var bolt_material := StandardMaterial3D.new()
	bolt_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	bolt_material.albedo_color = Color(0.12, 0.85, 1.0)
	bolt_material.emission_enabled = true
	bolt_material.emission = Color(0.04, 0.65, 1.0)
	bolt_material.emission_energy_multiplier = 5.0

	var bolt_mesh := SphereMesh.new()
	bolt_mesh.radius = 0.075
	bolt_mesh.height = 0.15
	bolt_mesh.radial_segments = 8
	bolt_mesh.rings = 4

	var bolt := MeshInstance3D.new()
	bolt.mesh = bolt_mesh
	bolt.material_override = bolt_material
	bolt.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	bolt.scale = Vector3(1.0, 1.0, 9.0)
	add_child(bolt)
