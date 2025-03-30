from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random

proyecto1 = Flask(__name__)
socketio = SocketIO(proyecto1)

# Variables Globales
barajas = {}
jugadores = {}
sala_host = {}
turno_actual = {}
carta_inicial_salas = {}  # Almacena la carta inicial de cada sala

colores = ["verde", "rojo", "azul", "amarillo"]
valores = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "prohibido", "cambioSentido", "+2"]
especiales = ["+4", "cambioColor"]

def crear_baraja():
    baraja = [{"Color": color, "valor": valor} for color in colores for valor in valores] * 2
    baraja.extend([{"Color": "Negro", "valor": valor} for valor in especiales] * 4)
    random.shuffle(baraja)
    return baraja

def repartir_baraja(sala):
    for id_jugador in jugadores[sala]:
        jugadores[sala][id_jugador]["mano"] = [barajas[sala].pop() for _ in range(7)]
    
    carta_inicial = barajas[sala].pop()
    while carta_inicial["valor"] in ["+4", "cambioColor"]:
        barajas[sala].append(carta_inicial)
        random.shuffle(barajas[sala])
        carta_inicial = barajas[sala].pop()
    
    return carta_inicial

@proyecto1.route("/")
def index():
    return render_template("index.html")

@socketio.on("unirse_sala")
def unirse_sala(datos):
    try:
        id_jugador = datos.get("id")
        nombre = datos.get("nombre")
        sala = datos.get("sala")

        if not id_jugador or not nombre or not sala:
            emit("error", {"mensaje": "Datos inválidos para unirse a la sala."}, room=request.sid)
            return

        join_room(sala)

        if sala not in jugadores:
            jugadores[sala] = {}
            barajas[sala] = crear_baraja()
            sala_host[sala] = id_jugador
            turno_actual[sala] = id_jugador
            carta_inicial_salas[sala] = None  # Inicialmente no hay carta inicial

        if id_jugador in jugadores[sala]:
            emit("cartas_repartidas", {"jugadores": jugadores[sala]}, room=request.sid)
            return

        jugadores[sala][id_jugador] = {"nombre": nombre, "mano": []}

        emit("mostrar_comenzar", {
            "host": sala_host[sala],
            "jugadores": list(jugadores[sala].values())
        }, room=sala)

    except Exception as e:
        print(f"Error al unir jugador a la sala: {str(e)}")
        emit("error", {"mensaje": "Ocurrió un error al unirse a la sala."}, room=request.sid)

@socketio.on("comenzar_juego")
def comenzar_juego(datos):
    sala = datos["sala"]
    carta_inicial_salas[sala] = repartir_baraja(sala)  # Guardamos la carta inicial

    emit("cartas_repartidas", {"jugadores": jugadores[sala]}, room=sala)
    emit("juego_comenzado", {
        "turno": turno_actual[sala],
        "carta_inicial": carta_inicial_salas[sala],
        "host": sala_host[sala]
    }, room=sala)

@socketio.on("obtener_estado")
def obtener_estado(datos):
    sala = datos["sala"]
    id_jugador = request.sid

    if sala in jugadores:
        # Asegurarnos de que siempre enviamos una carta inicial válida
        carta_inicial = carta_inicial_salas.get(sala, None)
        if carta_inicial is None and len(barajas[sala]) > 0:
            carta_inicial = barajas[sala].pop()
            carta_inicial_salas[sala] = carta_inicial  # Guardamos para futuras recargas
        
        emit("estado_actual", {
            "juegoActivo": True,
            "turno": turno_actual.get(sala, ""),
            "host": sala_host.get(sala, ""),
            "carta_inicial": carta_inicial  # Ahora siempre se enviará una carta inicial válida
        }, room=id_jugador)


@socketio.on("salir_sala")
def salir_sala(datos):
    id_jugador = datos["id"]
    sala = datos["sala"]

    if sala in jugadores and id_jugador in jugadores[sala]:
        leave_room(sala)
        del jugadores[sala][id_jugador]

        if sala_host[sala] == id_jugador and jugadores[sala]:
            sala_host[sala] = next(iter(jugadores[sala]))

        if not jugadores[sala]:
            del jugadores[sala]
            del barajas[sala]
            del sala_host[sala]
            del turno_actual[sala]
            del carta_inicial_salas[sala]

        emit("jugador_salio", {"id": id_jugador}, room=sala)

if __name__ == "__main__":
    socketio.run(proyecto1, debug=True)
