extends Area3D
## A straight-line tracer bolt. Detection is one-way: bullets carry
## mask=asteroids and invoke hit() on whatever they touch, then die.

var direction := Vector3.FORWARD
var speed := 260.0
var _life := 3.0


func _ready() -> void:
	add_to_group("bullets") # group-based lookup beats name matching: instanced
	# scene roots can land on auto-generated names like "@Area3D@14".
	area_entered.connect(_on_area_entered)


func _physics_process(delta: float) -> void:
	global_position += direction * speed * delta
	_life -= delta
	if _life <= 0.0:
		queue_free()


func _on_area_entered(area: Area3D) -> void:
	if area.is_in_group("asteroids") and area.has_method("hit"):
		area.hit()
		queue_free()
