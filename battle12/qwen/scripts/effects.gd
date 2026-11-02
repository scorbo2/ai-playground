class_name Effects
## Tiny FX library. Everything here is transient: spawned into the world,
## cleans itself up. No scene files needed - keeps the asset count low.

const DEBRIS_LIFE := 1.4


static func explode(origin: Vector3, radius: float, parent: Node) -> void:
	_spark_burst(origin, radius, parent)
	_flash_ball(origin, radius, parent)


static func _spark_burst(origin: Vector3, radius: float, parent: Node) -> void:
	var particles := GPUParticles3D.new()
	particles.amount = 48
	particles.lifetime = DEBRIS_LIFE
	particles.one_shot = true # 4.7 has no `explosive` - one-shot emission covers us
	particles.local_coords = false

	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	process.emission_sphere_radius = radius * 0.6
	process.spread = 180.0
	process.gravity = Vector3.ZERO
	process.initial_velocity_min = radius * 3.0
	process.initial_velocity_max = radius * 8.0
	process.damping_min = 0.4
	process.damping_max = 1.2
	process.scale_min = 0.08
	process.scale_max = 0.22
	particles.process_material = process

	var chunk := SphereMesh.new()
	chunk.radius = 1.0
	chunk.height = 2.0
	chunk.radial_segments = 6
	chunk.rings = 4
	var chunk_mat := StandardMaterial3D.new()
	chunk_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	chunk_mat.albedo_color = Color(1.0, 0.55, 0.2)
	# SurfaceTool lets us bake the material straight into an ArrayMesh -
	# far fewer wrapper-class gymnastics than touching mesh surface materials.
	var tool := SurfaceTool.new()
	tool.create_from(chunk, -1)
	tool.set_material(chunk_mat)
	particles.draw_pass_1 = tool.commit()

	parent.add_child(particles)
	particles.global_position = origin
	particles.emitting = true
	particles.finished.connect(particles.queue_free)


static func _flash_ball(origin: Vector3, radius: float, parent: Node) -> void:
	var flash := MeshInstance3D.new()
	var ball := SphereMesh.new()
	ball.radius = radius * 1.1
	ball.height = radius * 2.2
	ball.radial_segments = 12
	ball.rings = 8
	flash.mesh = ball
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(1.0, 0.85, 0.5, 0.9)
	flash.material_override = mat
	parent.add_child(flash)
	flash.global_position = origin

	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.6, 0.3)
	light.omni_range = radius * 8.0
	light.light_energy = 4.0
	parent.add_child(light)
	light.global_position = origin

	var tween := flash.create_tween()
	tween.set_parallel(true)
	tween.tween_property(flash, "scale", Vector3.ONE * 2.2, 0.35)
	tween.tween_property(mat, "albedo_color:a", 0.0, 0.45)
	tween.chain().tween_callback(flash.queue_free)

	var light_tween := light.create_tween()
	light_tween.tween_property(light, "light_energy", 0.0, 0.5)
	light_tween.tween_callback(light.queue_free)
