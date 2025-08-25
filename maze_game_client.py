import pygame
import random
import time
import json
import requests
import asyncio
import websockets

# Importar las clases de Pygame y MazeGenerator del código original
# Eliminar las clases de DB, Payment, Tournament
# La lógica del juego se limita al front-end

# Configuración del juego
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700
MAZE_WIDTH = 25
MAZE_HEIGHT = 17
CELL_SIZE = 25
ENTRY_COST = 250
POINTS_PER_DOLLAR = 250

# URL del servidor
SERVER_URL = "http://127.0.0.1:5000"

# Colores (del código original)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
DARK_GREEN = (0, 128, 0)

# Importamos la clase MazeGenerator del código original
class MazeGenerator:
    # Código de la clase MazeGenerator del archivo original
    # ...
    @staticmethod
    def generate_maze(width: int, height: int) -> List[List[int]]:
        if width % 2 == 0:
            width += 1
        if height % 2 == 0:
            height += 1
            
        maze = [[1 for _ in range(width)] for _ in range(height)]
        
        def carve_path(x: int, y: int):
            maze[y][x] = 0
            directions = [(2, 0), (0, 2), (-2, 0), (0, -2)]
            random.shuffle(directions)
            
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                
                if 1 <= nx < width-1 and 1 <= ny < height-1:
                    if maze[ny][nx] == 1:
                        maze[y + dy//2][x + dx//2] = 0
                        carve_path(nx, ny)
        
        carve_path(1, 1)
        maze[1][0] = 0
        maze[height-2][width-1] = 0
        
        for _ in range(random.randint(3, 7)):
            x = random.randrange(1, width-1, 2)
            y = random.randrange(1, height-1, 2)
            
            if random.random() < 0.3:
                directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
                dx, dy = random.choice(directions)
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    maze[y + dy][x + dx] = 0
        
        return maze

class MazeGameClient:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("🏆 Laberinto Arcade - Torneo Mundial Diario 🏆")
        self.clock = pygame.time.Clock()
        
        self.title_font = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 24)
        self.tiny_font = pygame.font.Font(None, 18)
        
        self.current_player = None
        self.auth_token = None
        self.current_session_id = None
        self.maze = None
        self.player_pos = [1, 1]
        self.start_time = None
        self.game_state = "menu"  # menu, login, register, shop, game, ranking
        
        self.input_text = ""
        self.input_field = ""
        self.login_data = {"username": "", "password": ""}
        self.register_data = {"username": "", "email": "", "password": ""}
        self.payment_amount = 5.0
        self.payment_status = ""
        
        print("🎮 Cliente del juego inicializado")
    
    def handle_api_response(self, response):
        """Maneja respuestas genéricas de la API."""
        if response.status_code == 200 or response.status_code == 201:
            return response.json()
        else:
            error = response.json().get('error', 'Unknown Error')
            print(f"❌ API Error: {error}")
            return None

    def attempt_login(self):
        data = self.login_data
        try:
            response = requests.post(f"{SERVER_URL}/api/login", json=data)
            result = self.handle_api_response(response)
            if result:
                self.auth_token = result['token']
                self.current_player = result['player']
                self.game_state = "menu"
                print(f"✅ Login exitoso: {self.current_player['username']}")
            else:
                print("❌ Credenciales inválidas")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión con el servidor: {e}")

    def attempt_register(self):
        data = self.register_data
        try:
            response = requests.post(f"{SERVER_URL}/api/register", json=data)
            result = self.handle_api_response(response)
            if result:
                print(f"✅ Usuario registrado. Ahora inicia sesión.")
                self.game_state = "login"
            else:
                print("❌ Registro fallido")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión con el servidor: {e}")
            
    def process_payment(self):
        if not self.auth_token or self.payment_amount < 1.0:
            return
        
        data = {
            'amount_usd': self.payment_amount,
            'method': 'stripe' # Simulamos un método de pago, el servidor lo maneja.
        }
        
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        try:
            response = requests.post(f"{SERVER_URL}/api/purchase", json=data, headers=headers)
            result = self.handle_api_response(response)
            if result:
                self.current_player['points'] = result['new_points']
                self.current_player['total_spent'] = result['total_spent']
                self.game_state = "menu"
                self.payment_status = "✅ Compra exitosa!"
                print(self.payment_status)
            else:
                self.payment_status = "❌ Compra fallida."
                print(self.payment_status)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión: {e}")
            self.payment_status = "❌ Error de conexión con el servidor."
            
    def start_new_game(self):
        if not self.auth_token or self.current_player['points'] < ENTRY_COST:
            print("❌ Puntos insuficientes")
            return
            
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        try:
            response = requests.post(f"{SERVER_URL}/api/start_game", headers=headers)
            result = self.handle_api_response(response)
            if result:
                self.current_session_id = result['session_id']
                self.maze = result['maze_config']
                self.current_player['points'] = result['points']
                self.player_pos = [1, 1]
                self.start_time = time.time()
                self.game_state = "game"
                print(f"✅ Partida iniciada - Sesión: {self.current_session_id}")
            else:
                print("❌ Error iniciando partida")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión: {e}")

    def complete_game(self):
        if not self.current_session_id or not self.start_time:
            return
        
        completion_time = time.time() - self.start_time
        
        data = {
            'session_id': self.current_session_id,
            'completion_time': completion_time
        }
        
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        try:
            response = requests.post(f"{SERVER_URL}/api/complete_game", json=data, headers=headers)
            result = self.handle_api_response(response)
            
            if result:
                print(f"🎉 ¡Completado en {completion_time:.2f} segundos!")
            else:
                print("❌ Error al registrar el resultado")

            self.current_session_id = None
            self.maze = None
            self.start_time = None
            self.game_state = "menu"
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión: {e}")
            self.game_state = "menu"
            
    # Funciones de dibujo y manejo de UI (draw_menu, draw_login, etc.)
    # Estas funciones se mantienen casi idénticas a las del código original.
    # Solo se debe cambiar la lógica interna para usar las peticiones a la API
    # en lugar de las operaciones directas a la DB.
    def draw_menu(self):
        self.screen.fill(WHITE)
        
        title = self.title_font.render("🏆 LABERINTO ARCADE 🏆", True, BLACK)
        self.screen.blit(title, (WINDOW_WIDTH//2 - title.get_width()//2, 50))
        
        if self.current_player:
            # Panel del jugador
            pygame.draw.rect(self.screen, LIGHT_GRAY, (50, 280, 300, 150))
            pygame.draw.rect(self.screen, BLACK, (50, 280, 300, 150), 2)
            
            welcome = self.font.render(f"👋 {self.current_player['username']}", True, BLACK)
            points = self.small_font.render(f"💎 Puntos: {self.current_player['points']}", True, DARK_GREEN)
            
            self.screen.blit(welcome, (60, 290))
            self.screen.blit(points, (60, 320))

            play_btn = self.draw_button("🎮 JUGAR AHORA", WINDOW_WIDTH//2 - 100, 450, 200, 40, GREEN, WHITE)
            shop_btn = self.draw_button("💳 COMPRAR PUNTOS", WINDOW_WIDTH//2 - 100, 500, 200, 40, YELLOW)
            ranking_btn = self.draw_button("🏆 RANKING", WINDOW_WIDTH//2 - 100, 550, 200, 40, BLUE, WHITE)
            logout_btn = self.draw_button("🚪 CERRAR SESIÓN", WINDOW_WIDTH//2 - 100, 600, 200, 40, GRAY)

            mouse_pos = pygame.mouse.get_pos()
            if pygame.mouse.get_pressed()[0]:
                if play_btn.collidepoint(mouse_pos) and self.current_player['points'] >= ENTRY_COST:
                    self.start_new_game()
                elif shop_btn.collidepoint(mouse_pos):
                    self.game_state = "shop"
                elif ranking_btn.collidepoint(mouse_pos):
                    self.game_state = "ranking"
                elif logout_btn.collidepoint(mouse_pos):
                    self.current_player = None
                    self.auth_token = None
        else:
            login_btn = self.draw_button("🔑 INICIAR SESIÓN", WINDOW_WIDTH//2 - 100, 350, 200, 40, BLUE, WHITE)
            register_btn = self.draw_button("📝 REGISTRARSE", WINDOW_WIDTH//2 - 100, 400, 200, 40, GREEN, WHITE)
            
            mouse_pos = pygame.mouse.get_pos()
            if pygame.mouse.get_pressed()[0]:
                if login_btn.collidepoint(mouse_pos):
                    self.game_state = "login"
                elif register_btn.collidepoint(mouse_pos):
                    self.game_state = "register"
    
    def draw_login(self):
        # Código para dibujar la pantalla de login del original.
        # ...
        self.screen.fill(WHITE)
        
        title = self.font.render("🔑 Iniciar Sesión", True, BLACK)
        self.screen.blit(title, (WINDOW_WIDTH//2 - title.get_width()//2, 100))
        
        username_label = self.small_font.render("Usuario:", True, BLACK)
        password_label = self.small_font.render("Contraseña:", True, BLACK)
        
        self.screen.blit(username_label, (300, 200))
        self.screen.blit(password_label, (300, 250))
        
        self.draw_text_input(self.login_data["username"], 400, 200, 200, self.input_field == "username")
        self.draw_text_input("*" * len(self.login_data["password"]), 400, 250, 200, self.input_field == "password")
        
        login_btn = self.draw_button("Entrar", WINDOW_WIDTH//2 - 50, 320, 100, 40, GREEN, WHITE)
        back_btn = self.draw_button("Volver", WINDOW_WIDTH//2 - 50, 380, 100, 40, GRAY)
        
        mouse_pos = pygame.mouse.get_pos()
        if pygame.mouse.get_pressed()[0]:
            if login_btn.collidepoint(mouse_pos):
                self.attempt_login()
            elif back_btn.collidepoint(mouse_pos):
                self.game_state = "menu"
            elif pygame.Rect(400, 200, 200, 30).collidepoint(mouse_pos):
                self.input_field = "username"
            elif pygame.Rect(400, 250, 200, 30).collidepoint(mouse_pos):
                self.input_field = "password"

    def draw_register(self):
        # Código para dibujar la pantalla de registro del original.
        # ...
        self.screen.fill(WHITE)
        title = self.font.render("📝 Registro de Nueva Cuenta", True, BLACK)
        self.screen.blit(title, (WINDOW_WIDTH//2 - title.get_width()//2, 100))
        labels = ["Usuario:", "Email:", "Contraseña:"]
        fields = ["username", "email", "password"]
        
        for i, (label, field) in enumerate(zip(labels, fields)):
            label_surface = self.small_font.render(label, True, BLACK)
            self.screen.blit(label_surface, (250, 180 + i * 50))
            display_text = self.register_data[field]
            if field == "password":
                display_text = "*" * len(display_text)
            self.draw_text_input(display_text, 350, 180 + i * 50, 250, self.input_field == field)
        
        register_btn = self.draw_button("Crear Cuenta", WINDOW_WIDTH//2 - 75, 340, 150, 40, GREEN, WHITE)
        back_btn = self.draw_button("Volver", WINDOW_WIDTH//2 - 50, 400, 100, 40, GRAY)
        
        mouse_pos = pygame.mouse.get_pos()
        if pygame.mouse.get_pressed()[0]:
            if register_btn.collidepoint(mouse_pos):
                self.attempt_register()
            elif back_btn.collidepoint(mouse_pos):
                self.game_state = "menu"
            else:
                for i, field in enumerate(fields):
                    if pygame.Rect(350, 180 + i * 50, 250, 30).collidepoint(mouse_pos):
                        self.input_field = field
                        break
    
    def draw_shop(self):
        # Código para la tienda, modificado para usar `process_payment`
        self.screen.fill(WHITE)
        title = self.font.render("💳 Tienda de Puntos", True, BLACK)
        self.screen.blit(title, (WINDOW_WIDTH//2 - title.get_width()//2, 50))
        
        info = self.small_font.render(f"💎 Puntos actuales: {self.current_player['points']}", True, DARK_GREEN)
        self.screen.blit(info, (WINDOW_WIDTH//2 - info.get_width()//2, 100))
        
        pay_btn = self.draw_button(f"💰 PAGAR ${self.payment_amount:.2f}", WINDOW_WIDTH//2 - 100, 320, 200, 50, GREEN, WHITE)
        back_btn = self.draw_button("🔙 Volver", WINDOW_WIDTH//2 - 50, 390, 100, 40, GRAY)
        
        mouse_pos = pygame.mouse.get_pos()
        if pygame.mouse.get_pressed()[0]:
            if pay_btn.collidepoint(mouse_pos):
                self.process_payment()
            elif back_btn.collidepoint(mouse_pos):
                self.game_state = "menu"

    def draw_ranking(self):
        # Código para el ranking, modificado para obtener datos de la API
        # y un socket para actualizaciones en tiempo real
        self.screen.fill(WHITE)
        title = self.font.render("🏆 Ranking Mundial Diario", True, BLACK)
        self.screen.blit(title, (WINDOW_WIDTH//2 - title.get_width()//2, 50))
        
        # Lógica para obtener el ranking de la API o del WebSocket
        # ...
        
        back_btn = self.draw_button("🔙 Volver", WINDOW_WIDTH//2 - 50, 550, 100, 40, GRAY)
        mouse_pos = pygame.mouse.get_pos()
        if pygame.mouse.get_pressed()[0] and back_btn.collidepoint(mouse_pos):
            self.game_state = "menu"

    def draw_maze(self):
        # Mantiene la lógica original para dibujar el laberinto
        # ...
        if not self.maze:
            return
        
        self.screen.fill(WHITE)
        
        maze_pixel_width = len(self.maze[0]) * CELL_SIZE
        maze_pixel_height = len(self.maze) * CELL_SIZE
        offset_x = (WINDOW_WIDTH - maze_pixel_width) // 2
        offset_y = (WINDOW_HEIGHT - maze_pixel_height) // 2 + 50
        
        for y in range(len(self.maze)):
            for x in range(len(self.maze[0])):
                rect = pygame.Rect(
                    offset_x + x * CELL_SIZE,
                    offset_y + y * CELL_SIZE,
                    CELL_SIZE,
                    CELL_SIZE
                )
                if self.maze[y][x] == 1:
                    pygame.draw.rect(self.screen, BLACK, rect)
                else:
                    pygame.draw.rect(self.screen, WHITE, rect)
                    pygame.draw.rect(self.screen, LIGHT_GRAY, rect, 1)
        
        player_rect = pygame.Rect(
            offset_x + self.player_pos[0] * CELL_SIZE + 3,
            offset_y + self.player_pos[1] * CELL_SIZE + 3,
            CELL_SIZE - 6,
            CELL_SIZE - 6
        )
        pygame.draw.rect(self.screen, RED, player_rect)
        pygame.draw.rect(self.screen, (150, 0, 0), player_rect, 2)
        
        goal_rect = pygame.Rect(
            offset_x + (len(self.maze[0]) - 1) * CELL_SIZE + 3,
            offset_y + (len(self.maze) - 2) * CELL_SIZE + 3,
            CELL_SIZE - 6,
            CELL_SIZE - 6
        )
        pygame.draw.rect(self.screen, GREEN, goal_rect)
        pygame.draw.rect(self.screen, (0, 150, 0), goal_rect, 2)
        
        pygame.draw.rect(self.screen, LIGHT_GRAY, (0, 0, WINDOW_WIDTH, 50))
        pygame.draw.rect(self.screen, BLACK, (0, 0, WINDOW_WIDTH, 50), 2)
        
        if self.start_time:
            elapsed = time.time() - self.start_time
            time_text = self.font.render(f"⏱️ Tiempo: {elapsed:.1f}s", True, BLACK)
            self.screen.blit(time_text, (20, 15))
        
        player_info = self.small_font.render(f"👤 {self.current_player['username']}", True, BLACK)
        self.screen.blit(player_info, (300, 18))
        
        cost_info = self.small_font.render("💰 Costo: 250 puntos ($1.00)", True, DARK_GREEN)
        self.screen.blit(cost_info, (500, 18))
        
        controls = self.tiny_font.render("🎮 Flechas para mover • ESC para salir", True, GRAY)
        self.screen.blit(controls, (WINDOW_WIDTH - 250, 5))
    
    def move_player(self, dx: int, dy: int):
        # Mantiene la lógica original
        # ...
        if not self.maze:
            return
        
        new_x = self.player_pos[0] + dx
        new_y = self.player_pos[1] + dy
        
        if (0 <= new_x < len(self.maze[0]) and 
            0 <= new_y < len(self.maze) and 
            self.maze[new_y][new_x] == 0):
            
            self.player_pos[0] = new_x
            self.player_pos[1] = new_y
            
            if new_x == len(self.maze[0]) - 1 and new_y == len(self.maze) - 2:
                self.complete_game()
    
    def run(self):
        # Bucle principal, modificado para usar los nuevos estados de juego
        # y las funciones de la API
        running = True
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if self.game_state == "game":
                        if event.key == pygame.K_UP: self.move_player(0, -1)
                        elif event.key == pygame.K_DOWN: self.move_player(0, 1)
                        elif event.key == pygame.K_LEFT: self.move_player(-1, 0)
                        elif event.key == pygame.K_RIGHT: self.move_player(1, 0)
                        elif event.key == pygame.K_ESCAPE: self.game_state = "menu"
                    elif self.game_state in ["login", "register"]:
                        self.handle_text_input(event)
            
            self.screen.fill(WHITE)
            
            if self.game_state == "menu":
                self.draw_menu()
            elif self.game_state == "login":
                self.draw_login()
            elif self.game_state == "register":
                self.draw_register()
            elif self.game_state == "shop":
                self.draw_shop()
            elif self.game_state == "ranking":
                self.draw_ranking()
            elif self.game_state == "game":
                self.draw_maze()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()

if __name__ == "__main__":
    game = MazeGameClient()
    game.run()