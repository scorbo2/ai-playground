shader_type sky;

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

float fbm(vec3 p) {
	float value = 0.0;
	float amplitude = 0.55;
	for (int octave = 0; octave < 4; octave++) {
		value += value_noise(p) * amplitude;
		p = p * 2.03 + vec3(1.7, 3.1, 2.4);
		amplitude *= 0.48;
	}
	return value;
}

vec3 stars(vec3 direction, float scale, float threshold) {
	vec3 p = direction * scale;
	vec3 cell = floor(p);
	vec3 offset = fract(p) - 0.5;
	float seed = hash31(cell);
	float point = (1.0 - smoothstep(0.025, 0.18, length(offset))) * step(threshold, seed);
	vec3 warm = vec3(1.0, 0.72, 0.52);
	vec3 cool = vec3(0.52, 0.76, 1.0);
	vec3 tint = mix(cool, warm, hash31(cell + 17.2));
	return tint * point * (0.7 + pow(seed, 18.0) * 4.0);
}

void sky() {
	vec3 direction = normalize(EYEDIR);
	float cloud = fbm(direction * 3.1 + vec3(2.0, 5.0, 1.0));
	float filaments = fbm(direction * 8.0 - vec3(3.0, 1.0, 4.0));
	float nebula_mask = smoothstep(0.40, 0.86, cloud + filaments * 0.24);
	float galactic_band = pow(max(0.0, 1.0 - abs(direction.y * 0.85 + direction.x * 0.30)), 4.0);
	vec3 base = mix(vec3(0.006, 0.010, 0.026), vec3(0.020, 0.028, 0.065), max(direction.y * 0.5 + 0.5, 0.0));
	base += vec3(0.025, 0.012, 0.060) * galactic_band;
	base += vec3(0.22, 0.040, 0.30) * nebula_mask * (0.45 + galactic_band * 0.65);
	base += vec3(0.015, 0.12, 0.18) * smoothstep(0.56, 0.96, filaments) * galactic_band;
	base += stars(direction, 210.0, 0.985);
	base += stars(direction, 410.0, 0.993) * 0.65;
	COLOR = base;
}
