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


colores = ["verde", "rojo", "azul", "amarillo", ]
valores = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "prohibido", "cambioSentido", "+2"]
especiales = ["+4", "cambioColor"]

def crear_baraja():
    baraja = [{"Color": color, "valor": valor} for color in colores for valor in valores] * 1
    baraja.extend([{"Color": "negro", "valor": valor} for valor in especiales] * 20)
    random.shuffle(baraja)
    return baraja

def repartir_baraja(sala):
    for id_jugador in jugadores[sala]:
        jugadores[sala][id_jugador]["mano"] = [barajas[sala].pop() for _ in range(7)]
    
    carta_inicial = barajas[sala].pop()
    while carta_inicial["valor"] in ["+4", "cambioColor","prohibido", "cambioSentido", "+2"]:
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
        id_jugador = str(datos.get("id"))
        nombre = datos.get("nombre")
        sala = datos.get("sala")

        # Depuración: Verificar qué valores llegan
        print(f"Datos recibidos - ID: {id_jugador}, Nombre: {nombre}, Sala: {sala}")

        if not id_jugador or not nombre or not sala:
            emit("error", {"mensaje": "Datos inválidos para unirse a la sala."}, room=request.sid)
            return

        if sala in jugadores and len(jugadores[sala])>=6:
            emit("error", {"mensaje" : "La sala a la que intentas entrar está llena, MAX 6 JUGADORES"},room=request.sid)
            return
        
        join_room(sala)

        if sala not in jugadores:
            jugadores[sala] = {}
            barajas[sala] = crear_baraja()
            sala_host[sala] = id_jugador
            turno_actual[sala] = id_jugador
            carta_inicial_salas[sala] = None  # Inicialmente no hay carta inicial

        # Aquí puede que ya exista un jugador en la sala, se debe comprobar si ya está presente
        if id_jugador in jugadores[sala]:
            emit("cartas_repartidas", {"jugadores": jugadores[sala]}, room=request.sid)
            return

        # Agregar jugador a la sala
        jugadores[sala][id_jugador] = {"nombre": nombre, "mano": []}

        # Depuración: Verificar el estado de 'jugadores' después de agregar el jugador
        print(f"Jugador {id_jugador} agregado. Estado actual de jugadores: {jugadores}")

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
    id_jugador = request.sid  # Obtener el ID del socket del jugador

    if sala in jugadores:
        carta_inicial = carta_inicial_salas.get(sala, None)

        # Si no hay carta inicial, seleccionamos una válida
        if carta_inicial is None and len(barajas[sala]) > 0:
            carta_inicial = barajas[sala].pop()
            carta_inicial_salas[sala] = carta_inicial  # Guardamos para futuras recargas

        # Asegurarnos de que el turno no esté vacío
        turno = turno_actual.get(sala, "")
        if not turno:
            turno = next(iter(jugadores[sala]))  # Si se perdió, asignar el primer jugador

        # Enviar el estado actualizado del juego
        emit("estado_actual", {
            "juegoActivo": True,
            "turno": turno,
            "host": sala_host.get(sala, ""),
            "carta_inicial": carta_inicial
        }, room=id_jugador)

        # Notificar a todos los jugadores el estado actualizado
        socketio.emit("estado_actualizado", {"turno": turno, "nueva_carta": carta_inicial}, room=sala)


@socketio.on("salir_sala")
def salir_sala(datos):
    id_jugador = str(datos["id"])
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


@socketio.on("validarCarta")
def validarCarta(datos):
    sala = datos["sala"]
    id_jugador = str(datos["id"])
    color = datos["color"]
    valor = datos["valor"]
    carta_seleccionada = {"Color": color, "valor": valor}

    if turno_actual.get(sala) != id_jugador:
        emit("error", {"mensaje": "No es tu turno."}, room=request.sid)
        return

    if carta_seleccionada in jugadores[sala][id_jugador]["mano"]:
        jugadores[sala][id_jugador]["mano"].remove(carta_seleccionada)

        if valor in ["+4", "cambioColor"]:  # Solo para cartas que requieren elección de color
            emit("elegir_color", {"id": id_jugador, "sala": sala}, room=request.sid)
            return  # Esperamos hasta que el jugador elija el color

        carta_inicial_salas[sala] = carta_seleccionada
        actualizar_turno(sala, id_jugador)



def actualizar_turno(sala,id_jugador):
    # Actualizar el turno actual al siguiente jugador
    
    if id_jugador not in jugadores[sala]:
        print(f"jugador {id_jugador} ya no esta en la sala")
        return
    
    ids_jugadores = list(jugadores[sala].keys())
    turno_index = ids_jugadores.index(id_jugador)
    siguiente_jugador = ids_jugadores[(turno_index + 1) % len(ids_jugadores)]
    turno_actual[sala] = siguiente_jugador

    # Emitir el estado actualizado a todos los jugadores de la sala
    estado_actual = {
        "turno": turno_actual[sala],
        "nueva_carta":carta_inicial_salas[sala],
        "jugadores": jugadores[sala],
        "juegoActivo": True  # El juego sigue activo
    }

    emit("estado_actualizado", estado_actual, room=sala)
    
    
@socketio.on("color_elegido")
def color_elegido(datos):
    id_jugador = datos["id"]
    sala = datos["sala"]
    color_elegido = datos["color"]

    if not sala or not id_jugador or not color_elegido:
        return

    carta_inicial_salas[sala] = {"Color": color_elegido, "valor": "cambioColor"}
    
    # Emitimos el cambio a todos
    emit("color_asignado", {"id": id_jugador, "sala": sala, "color": color_elegido}, room=sala)

    # Pasar el turno al siguiente jugador
    actualizar_turno(sala, id_jugador)


@socketio.on("solicitar_color")
def solicitar_color(datos):
    id_jugador = datos["id"]
    sala = datos["sala"]

    emit("elegir_color", {"id": id_jugador, "sala": sala}, room=request.sid)



@socketio.on("pasar_turno")
def pasar_turno(datos):
    sala = datos["sala"]
    id_jugador = str(datos["id"])
    
    # Verificar que la sala y el jugador existen
    if sala not in jugadores:
        print(f"Error: la sala {sala} no existe.")
        return

    if id_jugador not in jugadores[sala]:
        print(f"Error: el jugador {id_jugador} no existe en la sala {sala}.")
        return
    
    actualizar_turno(sala,id_jugador)
    

@socketio.on("robar_carta")
def robar_Carta(datos):
    sala = datos["sala"]
    id_jugador = str(datos["id"])
    
    #salir si no existe la sala o el jugador
    if sala not in jugadores or id_jugador not in jugadores[sala]:
        return
    #si hay cartas en el mazo/baraja, se roba una y se le da al jugador
    mazo = barajas[sala]
    if len(mazo) > 0 :    
        carta_robada = mazo.pop()
        jugadores[sala][id_jugador]["mano"].append(carta_robada)
        
        emit("cartas_robadas",{
            "id":id_jugador,"carta_robada": carta_robada,"mano":jugadores[sala][id_jugador]["mano"]},room=sala)
        
        emit("estado_actualizado", {
            "turno": turno_actual[sala],"jugadores": jugadores[sala],"juegoActivo": True,"nueva_carta":carta_inicial_salas[sala]}, room=sala)
    else:
        emit("error", {"mensaje": "El mazo está vacío. No puedes robar más cartas."}, room=request.sid)

if __name__ == "__main__":
    socketio.run(proyecto1, debug=True)
