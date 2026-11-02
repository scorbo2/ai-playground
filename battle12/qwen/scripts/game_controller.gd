extends Node3D
## Root of the game: wires HUD to gameplay, handles the death overlay
## and restart, and drags the star sphere along with the player so
## space never runs out.

@onready var _player: Area3D = $Player
@onready var _manager: Node3D = $AsteroidManager
@onready var _score_label: Label = $HUD/ScoreLabel
@onready var _crosshair: Label = $HUD/Crosshair
@onready var _overlay: ColorRect = $HUD/GameOverPanel
@onready var _overlay_label: Label = $HUD/GameOverPanel/GameOverLabel

@onready var _help_label: Label = $HUD/HelpLabel

var _dead := false


func _ready() -> void:
	_player.died.connect(_on_player_died)
	_manager.score_changed.connect(_on_score_changed)
	_overlay.visible = false
	_layout_hud()
	print("Asteroids3D: game running. Score updates via signal.")


func _layout_hud() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	_crosshair.position = viewport_size * 0.5 - Vector2(12, 16)
	# Keep the control hints pinned to the bottom edge on any window size.
	_help_label.offset_top = viewport_size.y - 44.0
	_help_label.offset_bottom = viewport_size.y - 12.0
	_help_label.offset_right = viewport_size.x - 24.0
	_overlay.size = viewport_size
	_overlay_label.position = viewport_size * 0.5 - Vector2(280, 40)


func _on_score_changed(new_score: int) -> void:
	_score_label.text = "SCORE: %d" % new_score


func _on_player_died() -> void:
	_dead = true
	_manager.spawn_enabled = false
	_manager.set_process(false)
	_overlay.visible = true
	print("Asteroids3D: player destroyed at %s" % _player.global_position)


func _unhandled_input(event: InputEvent) -> void:
	if (
		_dead
		and event is InputEventKey
		and event.pressed
		and (event.keycode == KEY_R or event.physical_keycode == KEY_R)
	):
		get_tree().reload_current_scene()
