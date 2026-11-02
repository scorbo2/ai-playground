extends CanvasLayer

signal restart_requested

const ReticleScript = preload("res://scripts/reticle.gd")

var _score_label: Label
var _score_caption_label: Label
var _speed_label: Label
var _drive_label: Label
var _asteroids_label: Label
var _proximity_label: Label
var _warning_label: Label
var _game_over_overlay: Control
var _final_score_label: Label
var _final_stats_label: Label
var _reticle: Control
var _time := 0.0
var _game_over := false

func _ready() -> void:
	layer = 10
	var root := Control.new()
	root.name = "CombatHUD"
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build_header(root)
	_build_footer(root)
	_build_reticle(root)
	_build_game_over(root)

func _process(delta: float) -> void:
	_time += delta
	if is_instance_valid(_warning_label):
		_warning_label.modulate.a = 0.55 + sin(_time * 8.0) * 0.35

func update_metrics(score: int, destroyed: int, speed: float, asteroid_count: int, nearest: float, boosting: bool) -> void:
	_score_label.text = "%06d" % score
	_score_caption_label.text = "SCORE // %03d KILLS" % destroyed
	_speed_label.text = "%03d M/S" % int(speed * 4.0)
	_drive_label.text = "BOOST ENGAGED" if boosting else "ION DRIVE NOMINAL"
	_drive_label.modulate = Color(1.0, 0.60, 0.26) if boosting else Color.WHITE
	_asteroids_label.text = "HOSTILES  %02d" % asteroid_count
	if nearest < 200.0:
		_proximity_label.text = "NEAREST   %03d M" % int(nearest)
	else:
		_proximity_label.text = "NEAREST   --- M"
	_warning_label.visible = nearest < 13.0 and not _game_over

func show_game_over(score: int, destroyed: int) -> void:
	_game_over = true
	_warning_label.visible = false
	_final_score_label.text = "SCORE  %06d" % score
	_final_stats_label.text = "%d ASTEROIDS DESTROYED" % destroyed
	_game_over_overlay.visible = true

func _build_header(root: Control) -> void:
	var score_panel := _make_panel(root)
	score_panel.offset_left = 20
	score_panel.offset_top = 20
	score_panel.offset_right = 238
	score_panel.offset_bottom = 106
	var score_box := _make_vbox(score_panel, 0)
	_score_caption_label = _make_label("SCORE // 000 KILLS", 11, Color(0.36, 0.72, 0.86))
	score_box.add_child(_score_caption_label)
	_score_label = _make_label("000000", 30, Color(0.90, 0.96, 1.0))
	score_box.add_child(_score_label)

	var title := _make_label("N E B U L A   S T R I K E", 19, Color(0.80, 0.93, 1.0))
	root.add_child(title)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.anchor_left = 0.5
	title.anchor_right = 0.5
	title.offset_left = -240
	title.offset_right = 240
	title.offset_top = 24
	title.offset_bottom = 52
	var sector := _make_label("DEEP FIELD  //  SECTOR 07", 10, Color(0.34, 0.57, 0.72))
	root.add_child(sector)
	sector.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sector.anchor_left = 0.5
	sector.anchor_right = 0.5
	sector.offset_left = -200
	sector.offset_right = 200
	sector.offset_top = 54
	sector.offset_bottom = 75

	var speed_panel := _make_panel(root)
	speed_panel.anchor_left = 1.0
	speed_panel.anchor_right = 1.0
	speed_panel.offset_left = -238
	speed_panel.offset_right = -20
	speed_panel.offset_top = 20
	speed_panel.offset_bottom = 106
	var speed_box := _make_vbox(speed_panel, 1)
	_speed_label = _make_label("060 M/S", 25, Color(0.90, 0.96, 1.0))
	_speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	speed_box.add_child(_speed_label)
	_drive_label = _make_label("ION DRIVE NOMINAL", 10, Color(0.36, 0.72, 0.86))
	_drive_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	speed_box.add_child(_drive_label)

func _build_footer(root: Control) -> void:
	var controls_panel := _make_panel(root)
	controls_panel.anchor_top = 1.0
	controls_panel.anchor_bottom = 1.0
	controls_panel.offset_left = 20
	controls_panel.offset_top = -101
	controls_panel.offset_right = 470
	controls_panel.offset_bottom = -20
	var controls_box := _make_vbox(controls_panel, 3)
	controls_box.add_child(_make_label("FLIGHT SYSTEMS", 10, Color(0.36, 0.72, 0.86)))
	controls_box.add_child(_make_label("W/S  PITCH    A/D  YAW    Q/E  ROLL", 12, Color(0.80, 0.88, 0.94)))
	controls_box.add_child(_make_label("SHIFT  BOOST    SPACE  FIRE    R  RELAUNCH", 12, Color(0.80, 0.88, 0.94)))

	var status_panel := _make_panel(root)
	status_panel.anchor_left = 1.0
	status_panel.anchor_right = 1.0
	status_panel.anchor_top = 1.0
	status_panel.anchor_bottom = 1.0
	status_panel.offset_left = -250
	status_panel.offset_right = -20
	status_panel.offset_top = -101
	status_panel.offset_bottom = -20
	var status_box := _make_vbox(status_panel, 5)
	status_box.add_child(_make_label("FIELD TELEMETRY", 10, Color(0.36, 0.72, 0.86)))
	_asteroids_label = _make_label("HOSTILES  00", 14, Color(0.88, 0.94, 1.0))
	_asteroids_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	status_box.add_child(_asteroids_label)
	_proximity_label = _make_label("NEAREST   --- M", 12, Color(0.65, 0.76, 0.85))
	_proximity_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	status_box.add_child(_proximity_label)

	_warning_label = _make_label("COLLISION WARNING", 18, Color(1.0, 0.25, 0.16))
	root.add_child(_warning_label)
	_warning_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_warning_label.anchor_left = 0.5
	_warning_label.anchor_right = 0.5
	_warning_label.anchor_top = 0.73
	_warning_label.anchor_bottom = 0.73
	_warning_label.offset_left = -180
	_warning_label.offset_right = 180
	_warning_label.offset_top = -20
	_warning_label.offset_bottom = 20
	_warning_label.visible = false

func _build_reticle(root: Control) -> void:
	_reticle = ReticleScript.new()
	root.add_child(_reticle)
	_reticle.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func _build_game_over(root: Control) -> void:
	_game_over_overlay = Control.new()
	_game_over_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_game_over_overlay)
	_game_over_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dimmer := ColorRect.new()
	dimmer.color = Color(0.003, 0.007, 0.018, 0.84)
	dimmer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_game_over_overlay.add_child(dimmer)
	dimmer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	_game_over_overlay.add_child(center)
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var panel := _make_panel(center)
	panel.custom_minimum_size = Vector2(480, 285)
	var box := _make_vbox(panel, 13)
	var title := _make_label("SHIP LOST", 38, Color(1.0, 0.30, 0.22))
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	var subtitle := _make_label("CATASTROPHIC HULL COLLISION", 12, Color(0.74, 0.58, 0.60))
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(subtitle)
	_final_score_label = _make_label("SCORE  000000", 25, Color(0.90, 0.96, 1.0))
	_final_score_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_final_score_label)
	_final_stats_label = _make_label("0 ASTEROIDS DESTROYED", 12, Color(0.46, 0.72, 0.84))
	_final_stats_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_final_stats_label)
	var restart_button := Button.new()
	restart_button.text = "RELAUNCH MISSION  [R]"
	restart_button.custom_minimum_size = Vector2(0, 44)
	restart_button.add_theme_font_size_override("font_size", 14)
	restart_button.pressed.connect(func() -> void: restart_requested.emit())
	box.add_child(restart_button)
	_game_over_overlay.visible = false

func _make_panel(parent: Node) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.012, 0.024, 0.048, 0.82)
	style.border_color = Color(0.12, 0.46, 0.62, 0.52)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 9
	style.content_margin_bottom = 9
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	return panel

func _make_vbox(parent: Node, separation: int) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_theme_constant_override("separation", separation)
	parent.add_child(box)
	return box

func _make_label(text: String, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label
