import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import display
from esphome.const import CONF_ID, CONF_PORT

DEPENDENCIES = ["wifi", "display"]

CONF_DISPLAY_ID = "display_id"
CONF_MAX_FRAME_SIZE = "max_frame_size"

tamagonion_display_ns = cg.esphome_ns.namespace("tamagonion_display")

TamagonionDisplay = tamagonion_display_ns.class_(
    "TamagonionDisplay",
    cg.Component,
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TamagonionDisplay),
        cv.Required(CONF_DISPLAY_ID): cv.use_id(display.Display),
        cv.Optional(CONF_PORT, default=18511): cv.port,
        cv.Optional(CONF_MAX_FRAME_SIZE, default=4096): cv.int_range(
            min=256, max=16384
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    disp = await cg.get_variable(config[CONF_DISPLAY_ID])

    cg.add(var.set_display(disp))
    cg.add(var.set_port(config[CONF_PORT]))
    cg.add(var.set_max_frame_size(config[CONF_MAX_FRAME_SIZE]))
