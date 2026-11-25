from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .session import engine, Base


class Usuarios(Base):
    __tablename__ = "Usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    nombre = Column(String, unique=True, nullable=False)
    avatar = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)

    cartas = relationship("UsuarioCarta", back_populates="usuario", cascade="all, delete")


class Cartas(Base):
    __tablename__ = "Cartas"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    id_api = Column(String, nullable=False)
    idioma = Column(String, default="es", nullable=False)
    nombre = Column(String, nullable=False)
    type = Column(String)
    price = Column(Float)
    rarity = Column(String)
    number = Column(String)
    set_id = Column(String)
    set_name = Column(String)
    stage = Column(String)
    especial_type = Column(String)
    trainer = Column(String)
    edition = Column(String)
    variantes_disponibles = Column(String, default="normal,reverse,holo")
    generacion = Column(String, nullable=True)
    pokedex_id = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint('id_api', 'idioma', name='uix_id_api_idioma'),
    )

    usuarios = relationship("UsuarioCarta", back_populates="carta", cascade="all, delete")


class UsuarioCarta(Base):
    __tablename__ = "usuario_carta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_nombre = Column(String, ForeignKey("Usuarios.nombre", ondelete="CASCADE"), nullable=False)
    carta_id = Column(String, ForeignKey("Cartas.id_api", ondelete="CASCADE"), nullable=False)
    idioma = Column(String, default="es", nullable=False)
    variante = Column(String, default="Normal", nullable=False)
    categoria = Column(String, nullable=True)
    cantidad = Column(Integer, default=1, nullable=False)

    usuario = relationship("Usuarios", back_populates="cartas", foreign_keys=[usuario_nombre])
    carta = relationship("Cartas", back_populates="usuarios", foreign_keys=[carta_id])


class Categoria(Base):
    __tablename__ = "Categoria"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    usuario_nombre = Column(String, ForeignKey("Usuarios.nombre", ondelete="CASCADE"), nullable=False)
    nombre = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint('usuario_nombre', 'nombre', name='uix_usuario_categoria'),
    )


class Mazo(Base):
    __tablename__ = "Mazo"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    usuario_nombre = Column(String, ForeignKey("Usuarios.nombre", ondelete="CASCADE"), nullable=False)
    nombre = Column(String, nullable=False)

    cartas = relationship("MazoCarta", back_populates="mazo", cascade="all, delete-orphan")


class MazoCarta(Base):
    __tablename__ = "MazoCarta"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    mazo_id = Column(Integer, ForeignKey("Mazo.id", ondelete="CASCADE"), nullable=False)
    id_api = Column(String, nullable=False)
    nombre_carta = Column(String, nullable=False)
    cantidad = Column(Integer, default=1, nullable=False)
    idioma = Column(String, default="es", nullable=False)
    edition = Column(String)

    mazo = relationship("Mazo", back_populates="cartas")


class CartaPrecio(Base):
    """Almacena precios comparativos por carta provenientes de múltiples APIs / mercados."""
    __tablename__ = "carta_precios"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    carta_id = Column(String, nullable=False, index=True)
    fuente = Column(String, nullable=False)  # Ej: TCGPlayer, TCGMatch, PokemonTCG, TCGCSV
    moneda = Column(String, default="USD", nullable=False)
    precio_usd = Column(Float, default=0.0, nullable=False)
    precio_original = Column(Float, default=0.0, nullable=False)
    precio_low = Column(Float, nullable=True)
    precio_mid = Column(Float, nullable=True)
    precio_high = Column(Float, nullable=True)
    variante = Column(String, default="market", nullable=True)
    actualizado_en = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint('carta_id', 'fuente', name='uix_carta_precio_fuente'),
    )


# Las tablas se crean desde main.py