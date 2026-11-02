extends Area3D
## Drifting, tumbling rock. No physics engine involvement - it just
## translates every frame, and Area3D overlaps handle all interactions.

var velocity := Vector3.ZERO
var spin_axis := Vector3.UP
var spin_speed := 0.5
var size := 1.0


func _ready() -> void:
	add_to_group("asteroids")


func setup(p_velocity: Vector3, p_size: float, p_spin_speed: float) -> void:
	velocity = p_velocity
	size = p_size
	scale = Vector3.ONE * p_size
	spin_speed = p_spin_speed
	spin_axis = Vector3(
		randf_range(-1.0, 1.0), randf_range(-1.0, 1.0), randf_range(-1.0, 1.0)
	).normalized()


func _physics_process(delta: float) -> void:
	global_position += velocity * delta
	rotate_object_local(spin_axis, spin_speed * delta)


func hit() -> void:
	var manager := get_tree().get_first_node_in_group("manager")
	if manager != null:
		manager.add_score(100)
	Effects.explode(global_position, size, get_parent())
	queue_free()
