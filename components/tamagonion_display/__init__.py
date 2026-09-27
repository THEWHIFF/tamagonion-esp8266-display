import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import display
from esphome.const import CONF_ID, CONF_PORT

DEPENDENCIES = ["display", "wifi"]

CONF_DISPLAY_ID = "display_id"
CONF_MAX_FRAME_SIZE = "max_frame_size"
CONF_PAIRING_CODE = "pairing_code"

DEFAULT_PORT = 18511
DEFAULT_MAX_FRAME_SIZE = 4096


tamagonion_display_ns = cg.esphome_ns.namespace("tamagonion_display")

TamagonionDisplay = tamagonion_display_ns.class_(
    "TamagonionDisplay",
    cg.Component,
)

PAIRING_CODE_SCHEMA = cv.All(
    cv.string_strict,
    cv.Length(min=8, max=64),
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TamagonionDisplay),
        cv.Required(CONF_DISPLAY_ID): cv.use_id(display.Display),
        cv.Required(CONF_PAIRING_CODE): PAIRING_CODE_SCHEMA,
        cv.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        cv.Optional(
            CONF_MAX_FRAME_SIZE,
            default=DEFAULT_MAX_FRAME_SIZE,
        ): cv.int_range(min=256, max=16384),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    component = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(component, config)

    display_component = await cg.get_variable(config[CONF_DISPLAY_ID])

    cg.add(component.set_display(display_component))
    cg.add(component.set_port(config[CONF_PORT]))
    cg.add(component.set_max_frame_size(config[CONF_MAX_FRAME_SIZE]))
    cg.add(component.set_pairing_code(config[CONF_PAIRING_CODE]))
