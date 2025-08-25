import os
import hashlib
import json
import uuid
import threading
import time
from datetime import datetime, timedelta, date
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

# Se reemplaza Flask con Flask-Sockets para la comunicación en tiempo real
from geventwebsocket.handler import WebSocketHandler
from gevent.pywsgi import WSGIServer
from gevent import spawn

from flask import Flask, request, jsonify
from flask_sockets import Sockets
import jwt
from dotenv import load_dotenv

import psycopg2
from psycopg2.extras import RealDictCursor

# Carga las variables de entorno del archivo .env
load_dotenv()

# Configuración del juego
ENTRY_COST = 250  # Puntos necesarios para jugar ($1 USD)
POINTS_PER_DOLLAR = 250  # 250 puntos = $1 USD
PRIZE_POOL_PERCENTAGE = 0.85  # 85% del total recaudado va al ganador, 15% comisión

# PostgreSQL Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'maze_game'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

SECRET_KEY = os.getenv('SECRET_KEY', 'your_super_secret_key') # Clave para JWT
if SECRET_KEY == 'your_super_secret_key':
    print("WARNING: Using default SECRET_KEY. Change it in your .env file!")

# Configuración de APIs de pago (simulado)
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
# No se usan en el servidor, ya que la comunicación con las APIs de pago
# se hace a través de webhooks o una comunicación segura.
# Esta es una versión simplificada.

app = Flask(__name__)
sockets = Sockets(app)

@dataclass
class Player:
    username: str
    email: str
    points: int
    password_hash: str
    total_spent: float = 0.0
    games_played: int = 0
    created_at: datetime = None
    last_payment: datetime = None

@dataclass
class GameSession:
    session_id: str
    player_username: str
    start_time: datetime
    end_time: Optional[datetime] = None
    completion_time: Optional[float] = None
    maze_config: str = ""
    is_winner: bool = False

class PostgreSQLManager:
    def __init__(self):
        self.conn_params = DB_CONFIG
        self.init_database()
    
    def get_connection(self):
        return psycopg2.connect(**self.conn_params)
    
    def init_database(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    username VARCHAR(50) PRIMARY KEY,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    points INTEGER DEFAULT 0,
                    password_hash VARCHAR(64) NOT NULL,
                    total_spent DECIMAL(10,2) DEFAULT 0.00,
                    games_played INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_payment TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_sessions (
                    session_id UUID PRIMARY KEY,
                    player_username VARCHAR(50) REFERENCES players(username),
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    completion_time DECIMAL(10,3),
                    maze_config TEXT,
                    is_winner BOOLEAN DEFAULT FALSE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id UUID PRIMARY KEY,
                    player_username VARCHAR(50) REFERENCES players(username),
                    amount_usd DECIMAL(10,2) NOT NULL,
                    points_purchased INTEGER NOT NULL,
                    payment_method VARCHAR(20) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    external_transaction_id VARCHAR(200),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    metadata JSONB
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_mazes (
                    date DATE PRIMARY KEY,
                    maze_config TEXT NOT NULL,
                    total_prize_pool DECIMAL(10,2) DEFAULT 0.00,
                    winner_username VARCHAR(50),
                    winner_time DECIMAL(10,3),
                    is_completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Base de datos PostgreSQL inicializada correctamente")
            
        except Exception as e:
            print(f"❌ Error inicializando la base de datos: {e}")

    # Otros métodos de la clase...
    # (create_player, authenticate_player, etc.)
    # Aquí puedes copiar los métodos que interactúan con la base de datos desde tu código original
    # Asegúrate de que las operaciones de la DB se hagan de forma segura y en el servidor.
    
    def get_player_by_username(self, username: str) -> Optional[Dict]:
        """Obtiene datos de un jugador por su nombre de usuario."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM players WHERE username = %s', (username,))
            player = cursor.fetchone()
            conn.close()
            return player
        except Exception as e:
            print(f"Error fetching player: {e}")
            return None
    
    def create_player(self, username: str, email: str, password: str) -> bool:
        """Crea un nuevo jugador"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            cursor.execute('''
                INSERT INTO players (username, email, password_hash)
                VALUES (%s, %s, %s)
            ''', (username, email, password_hash))
            
            conn.commit()
            conn.close()
            return True
        except psycopg2.IntegrityError:
            return False
        except Exception as e:
            print(f"Error creating player: {e}")
            return False

    def authenticate_player(self, username: str, password: str) -> Optional[Dict]:
        """Autentica un jugador"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            cursor.execute('''
                SELECT * FROM players 
                WHERE username = %s AND password_hash = %s AND is_active = TRUE
            ''', (username, password_hash))
            
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            print(f"Error in authentication: {e}")
            return None
            
    def add_points_after_payment(self, username: str, points: int, amount_usd: float, 
                                payment_method: str, external_tx_id: str) -> str:
        """Añade puntos después de un pago exitoso"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            transaction_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO transactions (transaction_id, player_username, amount_usd, 
                                        points_purchased, payment_method, status, external_transaction_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (transaction_id, username, amount_usd, points, payment_method, 'completed', external_tx_id))
            
            cursor.execute('''
                UPDATE players 
                SET points = points + %s, total_spent = total_spent + %s, last_payment = CURRENT_TIMESTAMP
                WHERE username = %s
            ''', (points, amount_usd, username))
            
            conn.commit()
            conn.close()
            return transaction_id
        except Exception as e:
            print(f"Error adding points: {e}")
            return ""

    def get_daily_maze(self, today: date) -> Optional[Dict]:
        """Obtiene o genera el laberinto diario"""
        # Aquí se usa el MazeGenerator del código original
        pass

    def start_game_session(self, username: str, maze_config: str) -> Optional[str]:
        """Inicia una nueva sesión de juego"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT points FROM players WHERE username = %s FOR UPDATE', (username,))
            current_points = cursor.fetchone()[0]
            
            if current_points < ENTRY_COST:
                conn.close()
                return None
            
            cursor.execute('''
                UPDATE players 
                SET points = points - %s, games_played = games_played + 1
                WHERE username = %s
            ''', (ENTRY_COST, username))
            
            session_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO game_sessions (session_id, player_username, maze_config)
                VALUES (%s, %s, %s)
            ''', (session_id, username, maze_config))
            
            conn.commit()
            conn.close()
            return session_id
        except Exception as e:
            print(f"Error starting game session: {e}")
            return None

    def complete_game_session(self, session_id: str, completion_time: float) -> bool:
        """Completa una sesión de juego"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE game_sessions 
                SET end_time = CURRENT_TIMESTAMP, completion_time = %s
                WHERE session_id = %s AND completion_time IS NULL
            ''', (completion_time, session_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error completing session: {e}")
            return False

    def get_daily_ranking(self, date_str: str) -> List[Dict]:
        """Obtiene el ranking diario"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT player_username, completion_time
                FROM game_sessions 
                WHERE DATE(start_time) = %s AND completion_time IS NOT NULL
                ORDER BY completion_time ASC
            ''', (date_str,))
            
            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            print(f"Error fetching ranking: {e}")
            return []

db_manager = PostgreSQLManager()

# Middleware de autenticación con JWT
def auth_required(f):
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authorization header is missing'}), 401
        
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = payload['username']
            request.user = db_manager.get_player_by_username(username)
            if not request.user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'error': str(e)}), 401
            
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__ # Necesario para Flask
    return wrapper

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'error': 'Missing data'}), 400

    if db_manager.create_player(username, email, password):
        return jsonify({'message': 'Registration successful'}), 201
    else:
        return jsonify({'error': 'Username or email already exists'}), 409

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    player = db_manager.authenticate_player(username, password)
    
    if player:
        payload = {'username': player['username'], 'exp': datetime.utcnow() + timedelta(hours=24)}
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return jsonify({
            'message': 'Login successful', 
            'token': token,
            'player': {
                'username': player['username'],
                'points': player['points'],
                'total_spent': str(player['total_spent'])
            }
        }), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/purchase', methods=['POST'])
@auth_required
def purchase_points():
    data = request.json
    amount_usd = data.get('amount_usd')
    method = data.get('method')
    username = request.user['username']
    
    if not amount_usd or not method:
        return jsonify({'error': 'Missing data'}), 400
    
    # Lógica de pago simulada y segura. En un sistema real,
    # se haría una petición a la API de pago y se esperaría
    # un webhook para confirmar la transacción.
    points_to_add = int(float(amount_usd) * POINTS_PER_DOLLAR)
    tx_id = f"simulated_{method}_{int(time.time())}"
    
    success = db_manager.add_points_after_payment(username, points_to_add, float(amount_usd), method, tx_id)
    
    if success:
        player_data = db_manager.get_player_by_username(username)
        return jsonify({
            'message': 'Purchase successful',
            'new_points': player_data['points'],
            'total_spent': str(player_data['total_spent'])
        }), 200
    else:
        return jsonify({'error': 'Purchase failed'}), 500

@app.route('/api/start_game', methods=['POST'])
@auth_required
def start_game():
    username = request.user['username']
    
    today = date.today()
    maze_data = db_manager.get_daily_maze(today)
    
    if not maze_data:
        return jsonify({'error': 'Could not get daily maze'}), 500

    session_id = db_manager.start_game_session(username, maze_data['maze_config'])
    
    if session_id:
        player_data = db_manager.get_player_by_username(username)
        return jsonify({
            'session_id': session_id,
            'maze_config': json.loads(maze_data['maze_config']),
            'points': player_data['points']
        }), 200
    else:
        return jsonify({'error': 'Insufficient points or other error'}), 400

@app.route('/api/complete_game', methods=['POST'])
@auth_required
def complete_game():
    data = request.json
    session_id = data.get('session_id')
    completion_time = data.get('completion_time')

    if not session_id or not completion_time:
        return jsonify({'error': 'Missing data'}), 400
    
    if db_manager.complete_game_session(session_id, completion_time):
        return jsonify({'message': 'Game completed successfully'}), 200
    else:
        return jsonify({'error': 'Failed to complete game'}), 500

@app.route('/api/ranking')
def get_ranking():
    today = date.today().strftime('%Y-%m-%d')
    ranking = db_manager.get_daily_ranking(today)
    
    total_entries = len(ranking)
    prize_pool = total_entries * (ENTRY_COST / POINTS_PER_DOLLAR) * PRIZE_POOL_PERCENTAGE
    
    return jsonify({
        'ranking': ranking,
        'prize_pool': prize_pool,
        'entry_cost_usd': ENTRY_COST / POINTS_PER_DOLLAR
    }), 200

@sockets.route('/ws/ranking')
def ranking_socket(ws):
    while not ws.closed:
        today = date.today().strftime('%Y-%m-%d')
        ranking = db_manager.get_daily_ranking(today)
        prize_pool = len(ranking) * (ENTRY_COST / POINTS_PER_DOLLAR) * PRIZE_POOL_PERCENTAGE
        
        ws.send(json.dumps({
            'ranking': ranking,
            'prize_pool': prize_pool
        }))
        time.sleep(5)  # Enviar ranking cada 5 segundos

def run_tournament_manager():
    def daily_reset():
        while True:
            now = datetime.now()
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            sleep_time = (tomorrow - now).total_seconds()
            
            print(f"Waiting for {sleep_time} seconds until daily prize reset.")
            time.sleep(sleep_time)
            
            process_daily_results()

    def process_daily_results():
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        ranking = db_manager.get_daily_ranking(yesterday)
        
        if ranking:
            winner = ranking[0]
            winner_username = winner['player_username']
            winner_time = winner['completion_time']
            
            total_participants = len(ranking)
            total_prize_usd = total_participants * (ENTRY_COST / POINTS_PER_DOLLAR)
            prize_to_winner = int(total_prize_usd * PRIZE_POOL_PERCENTAGE * POINTS_PER_DOLLAR)
            
            print(f"Daily winner for {yesterday}: {winner_username} with time {winner_time:.2f}s. Prize: {prize_to_winner} points.")
            
            try:
                conn = db_manager.get_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE daily_mazes SET total_prize_pool = %s, winner_username = %s, winner_time = %s, is_completed = TRUE WHERE date = %s',
                               (float(total_prize_usd), winner_username, float(winner_time), yesterday))
                cursor.execute('UPDATE players SET points = points + %s WHERE username = %s', (prize_to_winner, winner_username))
                conn.commit()
                conn.close()
                print("Prizes distributed and daily maze closed.")
            except Exception as e:
                print(f"Error distributing prizes: {e}")
        else:
            print(f"No participants for {yesterday}. No prizes to distribute.")
    
    # Inicia el hilo en un segundo plano
    threading.Thread(target=daily_reset, daemon=True).start()

if __name__ == '__main__':
    run_tournament_manager()
    print("🚀 Flask Server with Sockets running...")
    # Usa un servidor WSGI para manejar WebSockets
    http_server = WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()