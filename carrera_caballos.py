import pygame
import random
import os
import decimal
import sqlite3
import json
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
    "NUM_OPERACIONES": 3,
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

pygame.init()
fuente_nombres = pygame.font.SysFont("Verdana", 20, bold=True)
fuente_op = pygame.font.SysFont("Consolas", 35, bold=True)
fuente_ganador = pygame.font.SysFont("Impact", 60)
fuente_menu = pygame.font.SysFont("Impact", 50)
fuente_menu_small = pygame.font.SysFont("Verdana", 25)

NUMPAD_DIGITOS = {getattr(pygame, f"K_KP{i}"): str(i) for i in range(10)}
NUMPAD_DIGITOS[pygame.K_KP_PERIOD] = "."

# --- 2. Robustez de Datos (SQLite) ---
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
        """Recupera el total de aciertos y el total de intentos del historial."""
        self.cursor.execute('''
            SELECT COUNT(*), SUM(CASE WHEN es_correcta THEN 1 ELSE 0 END)
            FROM operaciones WHERE jugador = ?
        ''', (nombre_jugador,))
        total, aciertos = self.cursor.fetchone()
        return total if total else 0, aciertos if aciertos else 0

    def obtener_precision_historica(self, nombre_jugador):
        """Calcula la precisión histórica del jugador."""
        total, aciertos = self.obtener_stats_historicas(nombre_jugador)
        return (aciertos / total) if total > 0 else 0.5

    def obtener_tiempo_medio(self, nombre_jugador):
        """Calcula el tiempo medio de respuesta en milisegundos."""
        self.cursor.execute('''
            SELECT AVG(tiempo_ms) FROM operaciones WHERE jugador = ?
        ''', (nombre_jugador,))
        resultado = self.cursor.fetchone()[0]
        # Si no hay datos, retornar 5 segundos por defecto (5000 ms)
        return resultado if resultado else 5000.0

    def guardar(self, jugador, op, resp_j, resp_c, corr, diff, subz, tiempo):
        self.cursor.execute('''
            INSERT INTO operaciones (jugador, operacion, respuesta_jugador, respuesta_correcta, es_correcta, dificultad, subzona, tiempo_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (jugador, op, resp_j, resp_c, corr, diff, subz, tiempo))
        self.conn.commit()

DB = DatabaseManager(CONFIG["DB_NAME"])

# --- 3. Desacoplamiento Lógico (Strategy Pattern) ---
class NivelEstrategia:
    def generar(self, subzona): raise NotImplementedError

class Nivel1(NivelEstrategia):
    def generar(self, subzona):
        tipo = random.choice(["*", "/", "+", "-"])
        if tipo in ["+", "-"]:
            decimales = {"a": 1, "b": 2, "c": 3}[subzona]
            a = round(random.uniform(0.001, 10.000), decimales)
            b = round(random.uniform(0.001, 10.000), decimales)
            if tipo == "+": return f"{a} + {b}", round(a + b, decimales)
            if a < b: a, b = b, a
            return f"{a} - {b}", round(a - b, decimales)
        else:
            decimales = {"a": 1, "b": 2, "c": 2}[subzona] if tipo == "*" else {"a": 1, "b": 1, "c": 2}[subzona]
            a = round(random.uniform(0.1, 9.9), decimales)
            b = random.randint(2, 9)
            if tipo == "*": return f"{a} x {b}", round(a * b, decimales + 1)
            return f"{round(a * b, decimales + 1)} ÷ {b}", a

class Nivel2(NivelEstrategia):
    def generar(self, subzona):
        tipo = random.choice(["*", "/", "+", "-"])
        if tipo in ["+", "-"]:
            dec_a, dec_b = random.randint(1, 3), random.randint(2, 3)
            a = round(random.uniform(0.001, 10.000), dec_a)
            b = round(random.uniform(0.001, 10.000), dec_b)
            if tipo == "+": return f"{a} + {b}", round(a + b, max(dec_a, dec_b))
            if a < b: a, b = b, a
            return f"{a} - {b}", round(a - b, max(dec_a, dec_b))
        else:
            decimales = {"a": 1, "b": 2, "c": 2}[subzona] if tipo == "*" else {"a": 1, "b": 1, "c": 2}[subzona]
            dec_a, dec_b = random.randint(1, decimales), random.randint(1, decimales)
            a = round(random.uniform(1.1, 9.9), dec_a)
            b = round(random.uniform(1.1, 9.9), dec_b)
            if tipo == "*": return f"{a} x {b}", round(a * b, dec_a + dec_b)
            return f"{round(a * b, abs(dec_a + dec_b))} ÷ {b}", a

class OperacionFactory:
    @staticmethod
    def crear(factor_dificultad, subzona):
        estrategia = Nivel1() if factor_dificultad < 0.5 else Nivel2()
        return estrategia.generar(subzona)

# --- 4. Sistema de Eventos y Optimización ---
class Stats:
    def __init__(self, total_previo=0, aciertos_previos=0):
        self.total = total_previo
        self.aciertos = aciertos_previos
        # Calculamos la precisión inicial basada en el histórico
        self.accuracy = (self.aciertos / self.total) if self.total > 0 else 0.0
        self.streak = 0  # La racha suele reiniciarse por sesión de juego

    def registrar_respuesta(self, correcta):
        self.total += 1
        if correcta: self.aciertos += 1
        self.streak = self.streak + 1 if correcta else 0
        # Media acumulativa real
        self.accuracy = self.aciertos / self.total

    def get_nivel(self):
        if self.accuracy > 0.85: return 2
        if self.accuracy > 0.6: return 1
        return 0

    def get_subzona(self):
        if self.accuracy > 0.85: return "c"
        if self.accuracy > 0.6: return "b"
        return "a"

# --- 5. Gestión de Recursos (Asset Manager) ---
class AssetManager:
    _graficos = {}

    @classmethod
    def get_caballo(cls, path, color_default):
        if path in cls._graficos:
            return cls._graficos[path]
        
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
            except Exception: pass
            
        superficie = pygame.Surface((90, 60), pygame.SRCALPHA)
        pygame.draw.ellipse(superficie, color_default, (0, 0, 90, 60))
        cls._graficos[path] = [superficie]
        return cls._graficos[path]

# --- Lógica Base ---
class Caballo:
    def __init__(self, x, y, nombre, color, imagen_path, guardar_datos=False, es_fantasma=False, precision_fantasma=0.5, tiempo_medio_fantasma=5000):
        self.nombre = nombre
        self.color = color
        self.pos_y = y
        self.guardar_datos = guardar_datos
        self.es_fantasma = es_fantasma
        self.precision_fantasma = precision_fantasma
        self.tiempo_medio_fantasma = tiempo_medio_fantasma  # En milisegundos

        self.frames = AssetManager.get_caballo(imagen_path, color)
        self.frame_idx = 0
        self.last_anim = pygame.time.get_ticks()
        
        self.image = self.frames[0]
        self.rect = self.image.get_rect(topleft=(x, y))
        
        self.pos_x = float(x)
        self.target_x = float(x)
        self.meta_alcanzada = False
        
        # Timer para el fantasma
        self.last_intento_fantasma = pygame.time.get_ticks() if es_fantasma else 0
        
        if guardar_datos:
            try:
                total, aciertos = DB.obtener_stats_historicas(nombre)
                self.stats = Stats(total, aciertos)
            except Exception:
                self.stats = Stats()
        else:
            self.stats = Stats()

    def actualizar(self):
        # Animación
        ahora = pygame.time.get_ticks()
        if ahora - self.last_anim > 50:
            self.last_anim = ahora
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)
            self.image = self.frames[self.frame_idx]

        # Si es fantasma, intentar avanzar automáticamente cada t segundos
        if self.es_fantasma and not self.meta_alcanzada:
            if ahora - self.last_intento_fantasma >= self.tiempo_medio_fantasma:
                self.last_intento_fantasma = ahora
                self.avanzar_fantasma()

        # Movimiento fluido (Tweening/Lerp)
        if abs(self.target_x - self.pos_x) > 0.5:
            self.pos_x += (self.target_x - self.pos_x) * 0.08
            self.rect.x = int(self.pos_x)
        
        if self.rect.right >= CONFIG["META_X"]:
            self.meta_alcanzada = True

    def avanzar(self, pixeles):
        self.target_x += pixeles

    def avanzar_fantasma(self):
        """El caballo fantasma avanza según su precisión histórica"""
        if random.random() < self.precision_fantasma:
            self.avanzar(PIXELES_AVANZA)
            return True
        return False

    def dibujar(self, ventana):
        # Si es fantasma, aplicar efecto visual (semi-transparente)
        if self.es_fantasma:
            # Crear superficie temporal con alpha
            temp_surf = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
            temp_surf.blit(self.image, (0, 0))
            temp_surf.set_alpha(150)  # Semi-transparente
            ventana.blit(temp_surf, self.rect)
        else:
            ventana.blit(self.image, self.rect)
        
        # Nombre con estilo fantasma si corresponde
        color_texto = (180, 180, 200) if self.es_fantasma else (255, 255, 255)
        txt = fuente_nombres.render(self.nombre, True, color_texto)
        ventana.blit(txt, (self.rect.x, self.rect.y - 30))

class ManagerEntrada:
    def __init__(self, x, y, color_ui, caballo):
        self.rect_area = pygame.Rect(x, y, 350, 150)
        self.color = color_ui
        self.caballo = caballo
        self.input_text = ""
        self.mensaje = ""
        self.timer_msj = 0
        self.efecto_color = color_ui # Feedback visual
        
        self.generar_nueva_op()

    def generar_nueva_op(self):
        factor = self.caballo.stats.get_nivel() / 2.0
        subzona = self.caballo.stats.get_subzona()
        self.op_texto, self.op_res = OperacionFactory.crear(factor, subzona)
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

                # Actualizar Stats sin recalcular todo
                self.caballo.stats.registrar_respuesta(es_correcta)

                if self.caballo.guardar_datos:
                    DB.guardar(
                        self.caballo.nombre, self.op_texto, float(val), float(esperado), 
                        es_correcta, self.caballo.stats.get_nivel(), self.caballo.stats.get_subzona(), tiempo
                    )

                if es_correcta:
                    self.caballo.avanzar(PIXELES_AVANZA)
                    self.mensaje, self.efecto_color = "¡CORRECTO!", (0, 255, 0)
                else:
                    self.mensaje, self.efecto_color = "ERROR", (255, 50, 50)
                
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

def dibujar_campo(ventana):
    ventana.fill(CONFIG["COLOR_CESPED"])
    pygame.draw.rect(ventana, CONFIG["COLOR_TIERRA"], (0, 100, CONFIG["ANCHO"], 80))
    pygame.draw.rect(ventana, CONFIG["COLOR_TIERRA"], (0, 250, CONFIG["ANCHO"], 80))
    for y_line in [100, 180, 250, 330]:
        pygame.draw.line(ventana, (200, 200, 200), (0, y_line), (CONFIG["ANCHO"], y_line), 4)
    for i in range(0, 400, 40):
        color = (255, 255, 255) if i % 80 == 0 else (0, 0, 0)
        pygame.draw.rect(ventana, color, (CONFIG["META_X"], i + 50, 40, 40))

class Boton:
    def __init__(self, x, y, ancho, alto, texto, color_normal, color_hover):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.texto = texto
        self.color_normal = color_normal
        self.color_hover = color_hover
        self.color_actual = color_normal
        
    def dibujar(self, ventana, mouse_pos):
        # Cambiar color si el mouse está encima
        if self.rect.collidepoint(mouse_pos):
            self.color_actual = self.color_hover
        else:
            self.color_actual = self.color_normal
            
        # Dibujar botón
        pygame.draw.rect(ventana, self.color_actual, self.rect, border_radius=15)
        pygame.draw.rect(ventana, (255, 255, 255), self.rect, 3, border_radius=15)
        
        # Dibujar texto
        texto_render = fuente_menu_small.render(self.texto, True, (255, 255, 255))
        texto_rect = texto_render.get_rect(center=self.rect.center)
        ventana.blit(texto_render, texto_rect)
        
    def es_clickeado(self, mouse_pos):
        return self.rect.collidepoint(mouse_pos)

def menu_inicio():
    """Muestra el menú de inicio y retorna la modalidad elegida"""
    ventana = pygame.display.set_mode((CONFIG["ANCHO"], CONFIG["ALTO"]))
    pygame.display.set_caption("Hipódromo Matemático Pro - Menú")
    reloj = pygame.time.Clock()
    
    # Crear botones
    boton_2jugadores = Boton(250, 250, 500, 80, "2 JUGADORES", (50, 100, 255), (80, 130, 255))
    boton_fantasma = Boton(250, 360, 500, 80, "JUGADOR FANTASMA", (139, 0, 139), (169, 30, 169))
    
    # Verificar si hay datos históricos para modo fantasma
    total_j2, aciertos_j2 = DB.obtener_stats_historicas("JUGADOR 2")
    tiempo_medio_j2 = DB.obtener_tiempo_medio("JUGADOR 2")
    hay_historial = total_j2 > 0
    
    corriendo = True
    while corriendo:
        mouse_pos = pygame.mouse.get_pos()
        
        # Fondo
        ventana.fill(CONFIG["COLOR_CESPED"])
        
        # Título
        titulo = fuente_ganador.render("HIPÓDROMO MATEMÁTICO", True, (255, 255, 255))
        titulo_rect = titulo.get_rect(center=(CONFIG["ANCHO"] // 2, 120))
        ventana.blit(titulo, titulo_rect)
        
        subtitulo = fuente_menu_small.render("Selecciona el modo de juego", True, (255, 255, 255))
        subtitulo_rect = subtitulo.get_rect(center=(CONFIG["ANCHO"] // 2, 180))
        ventana.blit(subtitulo, subtitulo_rect)
        
        # Dibujar botones
        boton_2jugadores.dibujar(ventana, mouse_pos)
        boton_fantasma.dibujar(ventana, mouse_pos)
        
        # Información adicional
        if hay_historial:
            precision = (aciertos_j2 / total_j2) * 100
            tiempo_seg = tiempo_medio_j2 / 1000.0
            info1 = fuente_nombres.render(
                f"Historial J2: {total_j2} operaciones - {precision:.1f}% precisión", 
                True, (220, 220, 220)
            )
            info2 = fuente_nombres.render(
                f"Tiempo medio de respuesta: {tiempo_seg:.1f} segundos", 
                True, (220, 220, 220)
            )
            info1_rect = info1.get_rect(center=(CONFIG["ANCHO"] // 2, 470))
            info2_rect = info2.get_rect(center=(CONFIG["ANCHO"] // 2, 500))
            ventana.blit(info1, info1_rect)
            ventana.blit(info2, info2_rect)
        else:
            info = fuente_nombres.render(
                "No hay historial. El fantasma tendrá 50% precisión y 5s de respuesta.", 
                True, (220, 220, 220)
            )
            info_rect = info.get_rect(center=(CONFIG["ANCHO"] // 2, 480))
            ventana.blit(info, info_rect)
        
        # Instrucciones
        inst1 = fuente_nombres.render("2 JUGADORES: Compite contra otro jugador", True, (200, 200, 200))
        inst2 = fuente_nombres.render("FANTASMA: Compite contra el historial del Jugador 2", True, (200, 200, 200))
        ventana.blit(inst1, (120, 540))
        ventana.blit(inst2, (120, 570))
        
        # Eventos
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if boton_2jugadores.es_clickeado(mouse_pos):
                    return "dos_jugadores"
                elif boton_fantasma.es_clickeado(mouse_pos):
                    return "fantasma"
        
        pygame.display.flip()
        reloj.tick(60)
    
    return None

def loop_juego(modalidad):
    """Loop principal del juego según la modalidad"""
    ventana = pygame.display.set_mode((CONFIG["ANCHO"], CONFIG["ALTO"]))
    pygame.display.set_caption("Hipódromo Matemático Pro")
    reloj = pygame.time.Clock()

    gif = CONFIG["CABALLO_GIF"]
    
    if modalidad == "dos_jugadores":
        # Modo 2 jugadores tradicional
        caballo1 = Caballo(30, 105, "JUGADOR 1", (50, 100, 255), gif, guardar_datos=True)
        caballo2 = Caballo(30, 255, "JUGADOR 2", (255, 50, 50), gif, guardar_datos=True)
        
        ui1 = ManagerEntrada(80, 450, (50, 100, 255), caballo1)
        ui2 = ManagerEntrada(550, 450, (255, 50, 50), caballo2)
        
    else:  # modalidad == "fantasma"
        # Obtener precisión histórica y tiempo medio del jugador 2
        precision_fantasma = DB.obtener_precision_historica("JUGADOR 2")
        tiempo_medio_fantasma = DB.obtener_tiempo_medio("JUGADOR 2")
        
        # Caballo fantasma (shadow) basado en estadísticas del jugador 2
        caballo_shadow = Caballo(
            30, 105, "SHADOW (J2)", (100, 100, 120), gif, 
            guardar_datos=False, es_fantasma=True, 
            precision_fantasma=precision_fantasma,
            tiempo_medio_fantasma=tiempo_medio_fantasma
        )
        
        # Jugador real
        caballo_jugador = Caballo(30, 255, "JUGADOR 2", (255, 50, 50), gif, guardar_datos=True)
        
        # Solo UI para el jugador real, el fantasma se mueve automáticamente
        ui_jugador = ManagerEntrada(300, 450, (255, 50, 50), caballo_jugador)
        
        caballo1 = caballo_shadow
        caballo2 = caballo_jugador
        ui1 = None
        ui2 = ui_jugador

    corriendo = True
    ganador = None

    while corriendo:
        dibujar_campo(ventana)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                corriendo = False

            if event.type == pygame.KEYDOWN and not ganador:
                tecla, char = event.key, event.unicode
                
                if modalidad == "dos_jugadores":
                    # Jugador 1 (Teclado principal)
                    if tecla in range(pygame.K_0, pygame.K_9 + 1) or tecla in [pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_PERIOD, pygame.K_COMMA]:
                        ui1.procesar_tecla(tecla, char, tecla == pygame.K_BACKSPACE, tecla == pygame.K_RETURN)
                    
                    # Jugador 2 (Numpad)
                    if tecla in NUMPAD_DIGITOS or tecla in [pygame.K_DELETE, pygame.K_KP_ENTER]:
                        ui2.procesar_tecla(tecla, NUMPAD_DIGITOS.get(tecla, char), tecla == pygame.K_DELETE, tecla == pygame.K_KP_ENTER)
                
                else:  # modo fantasma
                    # Solo Jugador 2 con numpad
                    if tecla in NUMPAD_DIGITOS or tecla in [pygame.K_DELETE, pygame.K_KP_ENTER]:
                        ui2.procesar_tecla(tecla, NUMPAD_DIGITOS.get(tecla, char), tecla == pygame.K_DELETE, tecla == pygame.K_KP_ENTER)

        # Actualización fluida (Lerp y frames)
        caballo1.actualizar()
        caballo2.actualizar()

        caballo1.dibujar(ventana)
        caballo2.dibujar(ventana)
        
        if ui1:
            ui1.dibujar(ventana)
        ui2.dibujar(ventana)

        if not ganador:
            if caballo1.meta_alcanzada: 
                ganador = "¡EL SHADOW GANA!" if modalidad == "fantasma" else "¡EL JUGADOR 1 GANA!"
            elif caballo2.meta_alcanzada: 
                ganador = "¡EL JUGADOR 2 GANA!"

        if ganador:
            sombra = fuente_ganador.render(ganador, True, (0, 0, 0))
            texto = fuente_ganador.render(ganador, True, (255, 215, 0))
            ventana.blit(sombra, (CONFIG["ANCHO"] // 2 - sombra.get_width() // 2 + 4, 200 + 4))
            ventana.blit(texto, (CONFIG["ANCHO"] // 2 - texto.get_width() // 2, 200))
            
            # Instrucción para volver al menú
            inst = fuente_nombres.render("Presiona ESC para volver al menú", True, (255, 255, 255))
            ventana.blit(inst, (CONFIG["ANCHO"] // 2 - inst.get_width() // 2, 280))
            
            # Permitir salir al menú
            keys = pygame.key.get_pressed()
            if keys[pygame.K_ESCAPE]:
                return True  # Volver al menú

        pygame.display.flip()
        reloj.tick(CONFIG["FPS"])

    return False  # Salir del juego

def main():
    """Función principal que maneja el flujo del juego"""
    while True:
        modalidad = menu_inicio()
        
        if modalidad is None:
            break  # Salir del juego
        
        volver_menu = loop_juego(modalidad)
        
        if not volver_menu:
            break  # Salir del juego
    
    pygame.quit()

if __name__ == "__main__":
    main()