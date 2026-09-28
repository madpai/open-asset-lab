"""X9 copy of the Night Shift art package; X8's bytes remain historical."""
import art

PACKAGE = 'nightshift.assets_x9'


def library():
    lib = art.library()
    lib.id = PACKAGE
    lib.display_name = 'Night Shift visual production assets'
    bright = {'ceiling_light': 0.8, 'door_lamp': 1.4, 'status_lamp': 1.6,
              'alarm_light': 1.8, 'sign_aux': 0.8, 'sign_lift': 0.5,
              'sign_research': 0.5, 'sign_orders': 0.65, 'data_core': 0.5, 'console_desk': 0.22}
    metal = {'door_panel', 'shutter', 'valve_wheel', 'pump_piston', 'breaker_box'}
    for mat in lib.materials:
        name = mat.id.partition('/')[-1]
        mat.emissive = bright.get(name, 0.0)
        mat.roughness = 0.32 if name in metal else 0.55 if name in bright else 0.8
    for tex in lib.textures:
        if tex.id.endswith('/ceiling_light'):
            tex.rgba = art.tex_plain((58, 54, 48), (170, 146, 103)).rgba()
    return lib
