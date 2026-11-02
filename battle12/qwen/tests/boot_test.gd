extends SceneTree
## Headless boot entry: loads the real Main.tscn and attaches the test driver.


func _init() -> void:
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	current_scene = main
	var driver: Node = load("res://tests/test_driver.gd").new()
	root.add_child(driver)
