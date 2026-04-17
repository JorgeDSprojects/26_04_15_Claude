from sqladmin import Admin, ModelView

from app.models.asset import Asset
from app.models.asset_type import AssetType
from app.models.signal import Signal
from app.models.signal_type import SignalType


class AssetTypeAdmin(ModelView, model=AssetType):
    column_list = [AssetType.id, AssetType.name, AssetType.isa95_level]
    name = "Asset Type"
    name_plural = "Asset Types"
    icon = "fa-solid fa-layer-group"


class AssetAdmin(ModelView, model=Asset):
    column_list = [Asset.id, Asset.code, Asset.display_name, Asset.path]
    name = "Asset"
    name_plural = "Assets"
    icon = "fa-solid fa-wind"


class SignalTypeAdmin(ModelView, model=SignalType):
    column_list = [SignalType.id, SignalType.name, SignalType.description]
    name = "Signal Type"
    name_plural = "Signal Types"
    icon = "fa-solid fa-tags"


class SignalAdmin(ModelView, model=Signal):
    column_list = [
        Signal.id,
        Signal.name,
        Signal.display_name,
        Signal.topic,
        Signal.criticality,
        Signal.enabled,
    ]
    name = "Signal"
    name_plural = "Signals"
    icon = "fa-solid fa-signal"


def setup_admin(app, engine) -> Admin:
    admin = Admin(app, engine)
    admin.add_view(AssetTypeAdmin)
    admin.add_view(AssetAdmin)
    admin.add_view(SignalTypeAdmin)
    admin.add_view(SignalAdmin)
    return admin
