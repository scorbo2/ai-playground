extends Node3D

var model_scene: PackedScene
var surface_material: Material
var size := 2.0
var collision_radius := 2.0
var velocity := Vector3.ZERO
var spin := Vector3.ZERO
var frozen := false

func _ready() -> void:
	collision_radius = size * 1.08
	if model_scene == null:
		push_error("Asteroid requires a model scene.")
		return
	var model := model_scene.instantiate()
	model.name = "CrateredBasalt"
	add_child(model)
	scale = Vector3.ONE * size
	_apply_surface_material(model)

func _physics_process(delta: float) -> void:
	if frozen:
		return
	global_position += velocity * delta
	rotate_object_local(Vector3.RIGHT, spin.x * delta)
	rotate_object_local(Vector3.UP, spin.y * delta)
	rotate_object_local(Vector3.BACK, spin.z * delta)

func _apply_surface_material(node: Node) -> void:
	if node is MeshInstance3D and surface_material != null:
		for surface in range(node.mesh.get_surface_count()):
			node.set_surface_override_material(surface, surface_material)
	for child in node.get_children():
		_apply_surface_material(child)
