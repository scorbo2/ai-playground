extends Control

var _hit_flash := 0.0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func _process(delta: float) -> void:
	_hit_flash = maxf(0.0, _hit_flash - delta * 3.8)
	queue_redraw()

func register_hit() -> void:
	_hit_flash = 1.0

func _draw() -> void:
	var center := size * 0.5
	var color := Color(0.28, 0.86, 1.0, 0.82).lerp(Color(1.0, 0.55, 0.20, 1.0), _hit_flash)
	var radius := 15.0 + _hit_flash * 7.0
	draw_arc(center, radius, 0.15, 1.40, 20, color, 1.2, true)
	draw_arc(center, radius, 1.72, 2.97, 20, color, 1.2, true)
	draw_arc(center, radius, 3.29, 4.54, 20, color, 1.2, true)
	draw_arc(center, radius, 4.86, 6.11, 20, color, 1.2, true)
	draw_circle(center, 2.1 + _hit_flash * 1.8, color)
	draw_line(center + Vector2(-29, 0), center + Vector2(-21, 0), color, 1.0, true)
	draw_line(center + Vector2(21, 0), center + Vector2(29, 0), color, 1.0, true)
	draw_line(center + Vector2(0, -29), center + Vector2(0, -21), color, 1.0, true)
	draw_line(center + Vector2(0, 21), center + Vector2(0, 29), color, 1.0, true)
