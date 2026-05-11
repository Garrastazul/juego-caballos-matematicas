import pygame
import random
import os
import decimal
import sqlite3
import math
import json
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
from PIL import Image

# --- 1. Configuración Externa (JSON) ---
DEFAULT_CONFIG = {
    "ANCHO": 1000,
    "ALTO": 650,
    "FPS": 120,
    "COLOR_CESPED": [136, 179, 45],
    "COLOR_TIERRA": [139, 69, 19],
    "COLOR_META": [255, 255, 255],
    "META_X": 900,
    "NUM_OPERACIONES": 5,
    "DB_NAME": "estadisticas_juego.db",
    "CABALLO_GIF": "caballo.gif"
}

def cargar_configuracion():
    if not os.path.exists("config.json"):
        with open("config.json", "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    with open("config.json", "r") as f:
        return json.load(f)

CONFIG = cargar_configuracion()
PIXELES_AVANZA = (CONFIG["META_X"] - 30) / CONFIG["NUM_OPERACIONES"]
LERP_FACTOR = 0.05
UMBRAL = 0.5
FRAMES_MOVIMIENTO = int(math.ceil(math.log(UMBRAL / PIXELES_AVANZA) / math.log(1 - LERP_FACTOR)))
DURACION_SONIDO_CABALLO = int(FRAMES_MOVIMIENTO * 1000 / CONFIG["FPS"])

pygame.init()
pygame.mixer.init()

# --- 2. Sistema de Sonido Robusto ---
class SoundManager:
    def __init__(self):
        self.sounds = {}
        self.channels = {
            'sfx': pygame.mixer.Channel(0),
            'ambience': pygame.mixer.Channel(1)
        }
        
    def load(self, name, path):
        try:
            if path.lower().endswith('.mp3'):
                sound = self._load_mp3_safe(path)
            else:
                sound = pygame.mixer.Sound(path)
            self.sounds[name] = sound
            print(f"Sonido '{name}' cargado.")
        except Exception as e:
            print(f"No se pudo cargar '{name}': {e}")
            self.sounds[name] = None
            
    def _load_mp3_safe(self, path):
        try:
            return pygame.mixer.Sound(path)
        except:
            try:
                from pydub import AudioSegment
                sound = AudioSegment.from_mp3(path)
                temp_path = path.replace('.mp3', '_temp.wav')
                sound.export(temp_path, format='wav')
                loaded_sound = pygame.mixer.Sound(temp_path)
                os.remove(temp_path)
                return loaded_sound
            except ImportError:
                print("pydub no instalado, no se puede convertir MP3.")
                return None
            
    def play(self, name, maxtime=0):
        sound = self.sounds.get(name)
        if sound and not self.channels['sfx'].get_busy():
            self.channels['sfx'].play(sound, maxtime=maxtime)

sound_manager = SoundManager()
sound_manager.load('caballo', 'sonido_caballo.mp3')
sound_manager.load('error', 'error.mp3')

# --- 3. Estados del Juego ---
class GameState(Enum):
    MENU = "menu"
    PLAYING = "playing"
    FINISHED = "finished"
    QUIT = "quit"

# --- 4. Gestor de Renderizado ---
class Renderer:
    @staticmethod
    def dibujar_fondo(ventana):
        ventana.fill(CONFIG["COLOR_CESPED"])
        pygame.draw.rect(ventana, CONFIG["COLOR_TIERRA"], (0, 100, CONFIG["ANCHO"], 80))
        pygame.draw.rect(ventana, CONFIG["COLOR_TIERRA"], (0, 250, CONFIG["ANCHO"], 80))
        for y_line in [100, 180, 250, 330]:
            pygame.draw.line(ventana, (200, 200, 200), (0, y_line), (CONFIG["ANCHO"], y_line), 4)
        for i in range(0, 400, 40):
            color = (255, 255, 255) if i % 80 == 0 else (0, 0, 0)
            pygame.draw.rect(ventana, color, (CONFIG["META_X"], i + 50, 40, 40))

    @staticmethod
    def dibujar_menu(ventana, botones, mouse_pos, info_textos=None):
        # Solo fondo verde, sin el campo de carreras
        ventana.fill(CONFIG["COLOR_CESPED"])
        titulo = fuente_ganador.render("HIPÓDROMO MATEMÁTICO", True, (255, 255, 255))
        ventana.blit(titulo, (CONFIG["ANCHO"] // 2 - titulo.get_width() // 2, 120))
        subtitulo = fuente_menu_small.render("Selecciona el modo de juego", True, (255, 255, 255))
        ventana.blit(subtitulo, (CONFIG["ANCHO"] // 2 - subtitulo.get_width() // 2, 180))
        for boton in botones:
            boton.dibujar(ventana, mouse_pos)
        if info_textos:
            for texto, pos in info_textos:
                ventana.blit(texto, pos)

    @staticmethod
    def dibujar_juego(ventana, caballos, uis, ganador=None):
        Renderer.dibujar_fondo(ventana)
        for caballo in caballos:
            caballo.dibujar(ventana)
        for ui in uis:
            if ui:
                ui.dibujar(ventana)
        if ganador:
            Renderer.dibujar_ganador(ventana, ganador)

    @staticmethod
    def dibujar_ganador(ventana, texto_ganador):
        sombra = fuente_ganador.render(texto_ganador, True, (0, 0, 0))
        texto = fuente_ganador.render(texto_ganador, True, (255, 215, 0))
        ventana.blit(sombra, (CONFIG["ANCHO"] // 2 - sombra.get_width() // 2 + 4, 204))
        ventana.blit(texto, (CONFIG["ANCHO"] // 2 - texto.get_width() // 2, 200))
        inst = fuente_nombres.render("Presiona ESC para volver al menú", True, (255, 255, 255))
        ventana.blit(inst, (CONFIG["ANCHO"] // 2 - inst.get_width() // 2, 280))

# --- Fuentes globales ---
fuente_nombres = pygame.font.SysFont("Verdana", 20, bold=True)
fuente_op = pygame.font.SysFont("Consolas", 35, bold=True)
fuente_ganador = pygame.font.SysFont("Impact", 60)
fuente_menu = pygame.font.SysFont("Impact", 50)
fuente_menu_small = pygame.font.SysFont("Verdana", 25)

NUMPAD_DIGITOS = {getattr(pygame, f"K_KP{i}"): str(i) for i in range(10)}
NUMPAD_DIGITOS[pygame.K_KP_PERIOD] = "."

# --- Base de Datos (sin cambios) ---
class DatabaseManager:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS operaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jugador TEXT,
                operacion TEXT,
                respuesta_jugador REAL,
                respuesta_correcta REAL,
                es_correcta BOOLEAN,
                dificultad INTEGER,
                subzona TEXT,
                tiempo_ms INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def obtener_stats_historicas(self, nombre_jugador):
        self.cursor.execute('''
            SELECT COUNT(*), SUM(CASE WHEN es_correcta THEN 1 ELSE 0 END)
            FROM operaciones WHERE jugador = ?
        ''', (nombre_jugador,))
        total, aciertos = self.cursor.fetchone()
        return total if total else 0, aciertos if aciertos else 0

    def obtener_precision_historica(self, nombre_jugador):
        total, aciertos = self.obtener_stats_historicas(nombre_jugador)
        return (aciertos / total) if total > 0 else 0.5

    def obtener_tiempo_medio(self, nombre_jugador):
        self.cursor.execute('''
            SELECT AVG(tiempo_ms) FROM operaciones WHERE jugador = ?
        ''', (nombre_jugador,))
        resultado = self.cursor.fetchone()[0]
        return resultado if resultado else 5000.0

    def obtener_ultimas_respuestas(self, nombre_jugador, limite=20):
        self.cursor.execute('''
            SELECT es_correcta FROM operaciones 
            WHERE jugador = ? 
            ORDER BY id DESC LIMIT ?
        ''', (nombre_jugador, limite))
        filas = self.cursor.fetchall()
        return [bool(fila[0]) for fila in reversed(filas)]

    def guardar(self, jugador, op, resp_j, resp_c, corr, diff, subz, tiempo):
        self.cursor.execute('''
            INSERT INTO operaciones (jugador, operacion, respuesta_jugador, respuesta_correcta, es_correcta, dificultad, subzona, tiempo_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (jugador, op, resp_j, resp_c, corr, diff, subz, tiempo))
        self.conn.commit()

DB = DatabaseManager(CONFIG["DB_NAME"])

# --- Operaciones (sin cambios) ---
class OperacionBase:
    def generar(self, subzona): raise NotImplementedError

class Suma(OperacionBase):
    def generar(self, subzona):
        decimales = {"a": 1, "b": 2, "c": 3}[subzona]
        a = round(random.uniform(0.1, 10.000), decimales)
        dec_b = random.randint(1, decimales)
        b = round(random.uniform(0.1, 10.000), dec_b)
        return f"{a} + {b}", round(a + b, decimales)

class Resta(OperacionBase):
    def generar(self, subzona):
        decimales = {"a": 1, "b": 2, "c": 3}[subzona]
        a = round(random.uniform(0.1, 10.000), decimales)
        dec_b = random.randint(1, decimales)
        b = round(random.uniform(0.1, 10.000), dec_b)
        if a < b: a, b = b, a
        return f"{a} - {b}", round(a - b, decimales)

class Multiplicacion(OperacionBase):
    def generar(self, subzona):
        if subzona == "a":
            dec_a, dec_b = 1, 0
            a = round(random.uniform(0.1, 9.9), dec_a)
            b = random.randint(2, 9)
        elif subzona == "b":
            dec_a = random.randint(1, 2)
            dec_b = random.randint(1, max(1, 3 - dec_a))
            a = round(random.uniform(0.1, 9.99), dec_a)
            b = round(random.uniform(0.1, 9.99), dec_b)
        else:
            dec_a = random.randint(1, 3)
            dec_b = random.randint(1, max(1, 3 - dec_a))
            a = round(random.uniform(0.1, 9.999), dec_a)
            b = round(random.uniform(0.1, 9.999), dec_b)
        resultado = round(a * b, dec_a + dec_b)
        return f"{a} x {b}", resultado

class Division(OperacionBase):
    def generar(self, subzona):
        if subzona == "a":
            b = random.randint(2, 9)
            resultado = random.randint(1, 10)
            dividendo = resultado * b
            return f"{dividendo} ÷ {b}", resultado
        elif subzona == "b":
            b = random.randint(2, 9)
            dec_resultado = random.randint(1, 2)
            resultado = round(random.uniform(0.5, 9.99), dec_resultado)
            dividendo = round(resultado * b, 0)
            resultado = dividendo / b
            if resultado != round(resultado, dec_resultado):
                resultado = round(resultado, dec_resultado)
                dividendo = int(resultado * b)
            return f"{dividendo} ÷ {b}", resultado
        else:
            tipo = random.choice(["decimal_natural", "irracional_periodica"])
            if tipo == "decimal_natural":
                b = random.randint(2, 9)
                dec_dividendo = random.randint(1, 2)
                dividendo = round(random.uniform(1.0, 19.99), dec_dividendo)
                resultado = round(dividendo / b, 3)
            else:
                b = random.choice([3, 6, 7, 9])
                a = random.randint(1, 20)
                if random.random() < 0.5:
                    dividendo = a
                else:
                    dividendo = round(random.uniform(1.1, 19.9), 1)
                resultado = round(dividendo / b, 3)
            return f"{dividendo} ÷ {b}", resultado

class OperacionFactory:
    @staticmethod
    def crear(subzona):
        tipo = random.choice(['+', '-', '*', '/'])
        if tipo == '+': return Suma().generar(subzona)
        if tipo == '-': return Resta().generar(subzona)
        if tipo == '*': return Multiplicacion().generar(subzona)
        return Division().generar(subzona)

class Stats:
    def __init__(self, historial_inicial=None):
        self.window_size = 20
        self.historial = list(historial_inicial) if historial_inicial else []
        if len(self.historial) > self.window_size:
            self.historial = self.historial[-self.window_size:]
        self.streak = 0
        self.accuracy = self._calcular_precision()

    def _calcular_precision(self):
        if not self.historial: return 0.0
        return sum(self.historial) / len(self.historial)

    def registrar_respuesta(self, correcta):
        self.historial.append(correcta)
        if len(self.historial) > self.window_size: self.historial.pop(0)
        self.accuracy = self._calcular_precision()
        self.streak = self.streak + 1 if correcta else 0

    def get_subzona(self):
        if self.accuracy > 0.85: return "c"
        if self.accuracy > 0.6: return "b"
        return "a"

class AssetManager:
    _graficos = {}
    @classmethod
    def get_caballo(cls, path, color_default):
        if path in cls._graficos: return cls._graficos[path]
        frames = []
        if path and os.path.exists(path):
            try:
                gif = Image.open(path)
                for f in range(gif.n_frames):
                    gif.seek(f)
                    img = gif.convert("RGBA")
                    py_img = pygame.image.frombytes(img.tobytes(), img.size, img.mode)
                    frames.append(pygame.transform.scale(py_img, (100, 70)))
                cls._graficos[path] = frames
                return frames
            except: pass
        superficie = pygame.Surface((90, 60), pygame.SRCALPHA)
        pygame.draw.ellipse(superficie, color_default, (0, 0, 90, 60))
        cls._graficos[path] = [superficie]
        return cls._graficos[path]

class Caballo:
    def __init__(self, x, y, nombre, color, imagen_path, guardar_datos=False,
                 es_fantasma=False, precision_fantasma=0.5, tiempo_medio_fantasma=5000):
        self.nombre = nombre
        self.color = color
        self.pos_y = y
        self.guardar_datos = guardar_datos
        self.es_fantasma = es_fantasma
        self.precision_fantasma = precision_fantasma
        self.tiempo_medio_fantasma = tiempo_medio_fantasma
        self.frames = AssetManager.get_caballo(imagen_path, color)
        self.frame_idx = 0
        self.last_anim = pygame.time.get_ticks()
        self.image = self.frames[0]
        self.rect = self.image.get_rect(topleft=(x, y))
        self.pos_x = float(x)
        self.target_x = float(x)
        self.meta_alcanzada = False
        self.last_intento_fantasma = pygame.time.get_ticks() if es_fantasma else 0
        if guardar_datos:
            ultimas = DB.obtener_ultimas_respuestas(nombre)
            self.stats = Stats(historial_inicial=ultimas)
        else:
            self.stats = Stats()

    def actualizar(self, congelado=False):
        """Si 'congelado' es True, no se generan nuevos movimientos (ni fantasma), pero se sigue la interpolación."""
        ahora = pygame.time.get_ticks()
        if ahora - self.last_anim > 50:
            self.last_anim = ahora
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)
            self.image = self.frames[self.frame_idx]
        if self.es_fantasma and not self.meta_alcanzada and not congelado:
            if ahora - self.last_intento_fantasma >= self.tiempo_medio_fantasma:
                self.last_intento_fantasma = ahora
                self.avanzar_fantasma()
        if abs(self.target_x - self.pos_x) > 0.5:
            self.pos_x += (self.target_x - self.pos_x) * LERP_FACTOR
            self.rect.x = int(self.pos_x)
        if self.rect.right >= CONFIG["META_X"]:
            self.meta_alcanzada = True

    def avanzar(self, pixeles):
        self.target_x += pixeles
        sound_manager.play('caballo', maxtime=DURACION_SONIDO_CABALLO)

    def avanzar_fantasma(self):
        if random.random() < self.precision_fantasma:
            self.avanzar(PIXELES_AVANZA)
            return True
        return False

    def dibujar(self, ventana):
        if self.es_fantasma:
            temp_surf = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
            temp_surf.blit(self.image, (0, 0))
            temp_surf.set_alpha(150)
            ventana.blit(temp_surf, self.rect)
        else:
            ventana.blit(self.image, self.rect)
        color_texto = (180, 180, 200) if self.es_fantasma else (255, 255, 255)
        txt = fuente_nombres.render(self.nombre, True, color_texto)
        ventana.blit(txt, (self.rect.x, self.rect.y - 30))

    def esta_en_movimiento(self):
        """Devuelve True si aún se está interpolando hacia el objetivo."""
        return abs(self.target_x - self.pos_x) > 0.5

class ManagerEntrada:
    def __init__(self, x, y, color_ui, caballo):
        self.rect_area = pygame.Rect(x, y, 350, 150)
        self.color = color_ui
        self.caballo = caballo
        self.input_text = ""
        self.mensaje = ""
        self.timer_msj = 0
        self.efecto_color = color_ui
        self.generar_nueva_op()

    def generar_nueva_op(self):
        subzona = self.caballo.stats.get_subzona()
        self.op_texto, self.op_res = OperacionFactory.crear(subzona)
        self.start_time = pygame.time.get_ticks()

    def procesar_tecla(self, tecla, char, es_borrar, es_confirmar):
        if es_borrar:
            self.input_text = self.input_text[:-1]
        elif es_confirmar:
            try:
                entrada = self.input_text.replace(',', '.')
                val = Decimal(entrada)
                cuantizador = Decimal('1.' + '0' * len(entrada.split('.')[1])) if '.' in entrada else Decimal('1')
                esperado = Decimal(str(self.op_res)).quantize(cuantizador, rounding=ROUND_HALF_UP)
                tiempo = pygame.time.get_ticks() - self.start_time
                es_correcta = (val == esperado)
                self.caballo.stats.registrar_respuesta(es_correcta)
                if self.caballo.guardar_datos:
                    subzona_actual = self.caballo.stats.get_subzona()
                    DB.guardar(self.caballo.nombre, self.op_texto, float(val), float(esperado),
                               es_correcta, {"a":1, "b":2, "c":3}[subzona_actual], subzona_actual, tiempo)
                if es_correcta:
                    self.caballo.avanzar(PIXELES_AVANZA)
                    self.mensaje, self.efecto_color = "¡CORRECTO!", (0, 255, 0)
                else:
                    self.mensaje, self.efecto_color = "ERROR", (255, 50, 50)
                    sound_manager.play('error')
                self.generar_nueva_op()
            except decimal.InvalidOperation:
                self.mensaje, self.efecto_color = "VALOR INVÁLIDO", (255, 165, 0)
            self.input_text = ""
            self.timer_msj = pygame.time.get_ticks()
        else:
            if char in "0123456789.,":
                self.input_text += char

    def dibujar(self, ventana):
        color_borde = self.efecto_color if pygame.time.get_ticks() - self.timer_msj < 300 else self.color
        pygame.draw.rect(ventana, (0, 0, 0, 150), self.rect_area, border_radius=15)
        pygame.draw.rect(ventana, color_borde, self.rect_area, 4, border_radius=15)
        hud = f"Precisión: {self.caballo.stats.accuracy*100:.1f}% | Racha: {self.caballo.stats.streak}"
        ventana.blit(fuente_nombres.render(hud, True, (255, 255, 255)), (self.rect_area.x, self.rect_area.y - 30))
        ventana.blit(fuente_op.render(self.op_texto, True, (255, 255, 255)), (self.rect_area.x + 20, self.rect_area.y + 20))
        ventana.blit(fuente_op.render(self.input_text + "_", True, (255, 255, 0)), (self.rect_area.x + 20, self.rect_area.y + 80))
        if pygame.time.get_ticks() - self.timer_msj < 1200:
            ventana.blit(fuente_nombres.render(self.mensaje, True, color_borde), (self.rect_area.x + 20, self.rect_area.y + 125))

class Boton:
    def __init__(self, x, y, ancho, alto, texto, color_normal, color_hover):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.texto = texto
        self.color_normal = color_normal
        self.color_hover = color_hover
        self.color_actual = color_normal
        
    def dibujar(self, ventana, mouse_pos):
        if self.rect.collidepoint(mouse_pos):
            self.color_actual = self.color_hover
        else:
            self.color_actual = self.color_normal
        pygame.draw.rect(ventana, self.color_actual, self.rect, border_radius=15)
        pygame.draw.rect(ventana, (255, 255, 255), self.rect, 3, border_radius=15)
        texto_render = fuente_menu_small.render(self.texto, True, (255, 255, 255))
        ventana.blit(texto_render, (self.rect.x + self.rect.width//2 - texto_render.get_width()//2,
                                    self.rect.y + self.rect.height//2 - texto_render.get_height()//2))
        
    def es_clickeado(self, mouse_pos):
        return self.rect.collidepoint(mouse_pos)

# --- Clase principal del juego (máquina de estados con finalización suave) ---
class Game:
    def __init__(self):
        self.ventana = pygame.display.set_mode((CONFIG["ANCHO"], CONFIG["ALTO"]))
        pygame.display.set_caption("Hipódromo Matemático Pro")
        self.reloj = pygame.time.Clock()
        self.state = GameState.MENU
        self.modalidad = None
        self.caballos = []
        self.uis = []
        self.ganador = None
        self.congelado = False

    def run(self):
        while self.state != GameState.QUIT:
            if self.state == GameState.MENU:
                self.handle_menu()
            elif self.state == GameState.PLAYING:
                self.handle_playing()
            elif self.state == GameState.FINISHED:
                self.handle_finished()
            pygame.display.flip()
            self.reloj.tick(CONFIG["FPS"])
        pygame.quit()

    def handle_menu(self):
        botones = [
            Boton(250, 250, 500, 80, "2 JUGADORES", (50, 100, 255), (80, 130, 255)),
            Boton(250, 360, 500, 80, "JUGADOR FANTASMA", (139, 0, 139), (169, 30, 169))
        ]
        total_j2, aciertos_j2 = DB.obtener_stats_historicas("JUGADOR 2")
        tiempo_medio_j2 = DB.obtener_tiempo_medio("JUGADOR 2")
        hay_historial = total_j2 > 0

        while self.state == GameState.MENU:
            mouse_pos = pygame.mouse.get_pos()
            info_textos = []
            if hay_historial:
                precision = (aciertos_j2 / total_j2) * 100
                tiempo_seg = tiempo_medio_j2 / 1000.0
                info1 = fuente_nombres.render(f"Historial J2: {total_j2} operaciones - {precision:.1f}% precisión", True, (220, 220, 220))
                info2 = fuente_nombres.render(f"Tiempo medio de respuesta: {tiempo_seg:.1f} segundos", True, (220, 220, 220))
                info_textos.append((info1, (CONFIG["ANCHO"]//2 - info1.get_width()//2, 470)))
                info_textos.append((info2, (CONFIG["ANCHO"]//2 - info2.get_width()//2, 500)))
            else:
                info = fuente_nombres.render("No hay historial. Fantasma: 50% precisión, 5s respuesta.", True, (220, 220, 220))
                info_textos.append((info, (CONFIG["ANCHO"]//2 - info.get_width()//2, 480)))

            Renderer.dibujar_menu(self.ventana, botones, mouse_pos, info_textos)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.state = GameState.QUIT
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if botones[0].es_clickeado(mouse_pos):
                        self.modalidad = "dos_jugadores"
                        self.state = GameState.PLAYING
                    elif botones[1].es_clickeado(mouse_pos):
                        self.modalidad = "fantasma"
                        self.state = GameState.PLAYING
            pygame.display.flip()
            self.reloj.tick(60)

    def handle_playing(self):
        gif = CONFIG["CABALLO_GIF"]
        if self.modalidad == "dos_jugadores":
            caballo1 = Caballo(30, 105, "JUGADOR 1", (50, 100, 255), gif, guardar_datos=True)
            caballo2 = Caballo(30, 255, "JUGADOR 2", (255, 50, 50), gif, guardar_datos=True)
            ui1 = ManagerEntrada(80, 450, (50, 100, 255), caballo1)
            ui2 = ManagerEntrada(550, 450, (255, 50, 50), caballo2)
            self.caballos = [caballo1, caballo2]
            self.uis = [ui1, ui2]
        else:
            precision_fantasma = DB.obtener_precision_historica("JUGADOR 2")
            tiempo_medio_fantasma = DB.obtener_tiempo_medio("JUGADOR 2")
            caballo_shadow = Caballo(30, 105, "SHADOW (J2)", (100, 100, 120), gif,
                                     guardar_datos=False, es_fantasma=True,
                                     precision_fantasma=precision_fantasma,
                                     tiempo_medio_fantasma=tiempo_medio_fantasma)
            caballo_jugador = Caballo(30, 255, "JUGADOR 2", (255, 50, 50), gif, guardar_datos=True)
            ui_jugador = ManagerEntrada(300, 450, (255, 50, 50), caballo_jugador)
            self.caballos = [caballo_shadow, caballo_jugador]
            self.uis = [None, ui_jugador]

        self.ganador = None
        self.congelado = False

        while self.state == GameState.PLAYING:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.state = GameState.QUIT
                elif event.type == pygame.KEYDOWN and not self.congelado:
                    tecla, char = event.key, event.unicode
                    if self.modalidad == "dos_jugadores":
                        if tecla in range(pygame.K_0, pygame.K_9 + 1) or tecla in [pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_PERIOD, pygame.K_COMMA]:
                            self.uis[0].procesar_tecla(tecla, char, tecla == pygame.K_BACKSPACE, tecla == pygame.K_RETURN)
                        if tecla in NUMPAD_DIGITOS or tecla in [pygame.K_DELETE, pygame.K_KP_ENTER]:
                            self.uis[1].procesar_tecla(tecla, NUMPAD_DIGITOS.get(tecla, char), tecla == pygame.K_DELETE, tecla == pygame.K_KP_ENTER)
                    else:
                        if tecla in NUMPAD_DIGITOS or tecla in [pygame.K_DELETE, pygame.K_KP_ENTER]:
                            self.uis[1].procesar_tecla(tecla, NUMPAD_DIGITOS.get(tecla, char), tecla == pygame.K_DELETE, tecla == pygame.K_KP_ENTER)
            
            # Actualizar caballos (congelado controla si se permiten nuevos movimientos)
            for caballo in self.caballos:
                caballo.actualizar(congelado=self.congelado)

            # Verificar ganador
            if not self.ganador:
                for caballo in self.caballos:
                    if caballo.meta_alcanzada:
                        self.ganador = "¡EL SHADOW GANA!" if (self.modalidad == "fantasma" and caballo.es_fantasma) else \
                                       "¡EL JUGADOR 1 GANA!" if caballo == self.caballos[0] else "¡EL JUGADOR 2 GANA!"
                        self.congelado = True  # Desactiva entrada y avance fantasma
                        break

            # Si hay ganador, verificar si los caballos ya terminaron su movimiento
            if self.congelado:
                todos_quietos = all(not caballo.esta_en_movimiento() for caballo in self.caballos)
                if todos_quietos:
                    self.state = GameState.FINISHED

            Renderer.dibujar_juego(self.ventana, self.caballos, self.uis, self.ganador)
            pygame.display.flip()
            self.reloj.tick(CONFIG["FPS"])

    def handle_finished(self):
        while self.state == GameState.FINISHED:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.state = GameState.QUIT
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.state = GameState.MENU
                        return
            Renderer.dibujar_juego(self.ventana, self.caballos, self.uis, self.ganador)
            pygame.display.flip()
            self.reloj.tick(CONFIG["FPS"])

if __name__ == "__main__":
    juego = Game()
    juego.run()