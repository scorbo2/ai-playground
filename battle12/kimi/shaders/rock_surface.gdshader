shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

varying vec3 local_position;

float hash31(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.yzx + 33.33);
	return fract((p.x + p.y) * p.z);
}

float value_noise(vec3 p) {
	vec3 cell = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(
		mix(mix(hash31(cell), hash31(cell + vec3(1,0,0)), f.x),
			mix(hash31(cell + vec3(0,1,0)), hash31(cell + vec3(1,1,0)), f.x), f.y),
		mix(mix(hash31(cell + vec3(0,0,1)), hash31(cell + vec3(1,0,1)), f.x),
			mix(hash31(cell + vec3(0,1,1)), hash31(cell + vec3(1,1,1)), f.x), f.y), f.z);
}

void vertex() {
	local_position = VERTEX;
}

void fragment() {
	float broad_minerals = value_noise(local_position * 4.8);
	float fine_grain = value_noise(local_position * 22.0);
	float pits = smoothstep(0.26, 0.72, value_noise(local_position * 11.0));
	vec3 mineral_tint = COLOR.rgb * (0.10 + broad_minerals * 0.28);
	mineral_tint *= 0.76 + fine_grain * 0.34;
	mineral_tint += vec3(0.003, 0.004, 0.007) * pits;
	ALBEDO = mineral_tint;
	ROUGHNESS = 0.94;
	METALLIC = 0.045;
	SPECULAR = 0.24;
}
