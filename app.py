import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv
from datetime import datetime
import json

# 로컬 환경에서는 .env를 읽고, Azure에서는 패스.
if os.path.exists('.env'):
    load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 데이터베이스 연결 함수
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),        
        # sslmode='require' #Azure를 위해 반드시 추가
    )
    print('get_db_connection', conn)
    conn.autocommit = True
    return conn

@app.route('/')
def index():
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    print('get_db_connection', conn)
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. SELECT
    cursor.execute("SELECT id, title, author, created_at, view_count, like_count FROM board.posts ORDER BY created_at DESC")
    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    # 3. index.html 파일에 변수로 넘겨주기
    return render_template('index.html', posts = posts)

@app.route('/create/', methods=['GET'] )
def create_form():
    return render_template('create.html')

@app.route('/create/',methods=['POST']  )
def create_post():
    #1. 폼에 있는 정보들을 get
    title = request.form.get('title')
    author = request.form.get('author')
    content = request.form.get('content')

    if not title or not author or not content:
        flash('모든 필드를 똑바로 채워주세요!!!!')
        return redirect(url_for('create_form'))
    
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. INSERT
    cursor.execute("INSERT INTO board.posts (title, content, author) VALUES (%s, %s, %s) RETURNING id", (title,author,content ))
    post_id = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    flash('게시글이 성공적으로 등록되었음')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('UPDATE board.posts SET view_count = view_count + 1 WHERE id = %s', (post_id,))
    
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    
    if post is None:
        cursor.close()
        conn.close()
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    cursor.execute('SELECT * FROM board.comments WHERE post_id = %s ORDER BY created_at', (post_id,))
    comments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    user_ip = request.remote_addr
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    liked = cursor.fetchone()[0] > 0
    cursor.close()
    conn.close()
    
    return render_template('view.html', post=post, comments=comments, liked=liked)

@app.route('/edit/<int:post_id>', methods=['GET'])
def edit_form(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if post is None:
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    return render_template('edit.html', post=post)

@app.route('/edit/<int:post_id>', methods=['POST'])
def edit_post(post_id):
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not title or not content:
        flash('제목과 내용을 모두 입력해주세요.')
        return redirect(url_for('edit_form', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE board.posts SET title = %s, content = %s, updated_at = %s WHERE id = %s',
        (title, content, datetime.now(), post_id)
    )
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 수정되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM board.posts WHERE id = %s', (post_id,))
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 삭제되었습니다.')
    return redirect(url_for('index'))

@app.route('/post/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    author = request.form.get('author')
    content = request.form.get('content')
    
    if not author or not content:
        flash('작성자와 내용을 모두 입력해주세요.')
        return redirect(url_for('view_post', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO board.comments (post_id, author, content) VALUES (%s, %s, %s)',
        (post_id, author, content)
    )
    cursor.close()
    conn.close()
    
    flash('댓글이 등록되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/like/<int:post_id>', methods=['POST'])
def like_post(post_id):
    user_ip = request.remote_addr
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    already_liked = cursor.fetchone()[0] > 0
    
    if already_liked:
        cursor.execute('DELETE FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count - 1 WHERE id = %s', (post_id,))
        message = '좋아요가 취소되었습니다.'
    else:
        cursor.execute('INSERT INTO board.likes (post_id, user_ip) VALUES (%s, %s)', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count + 1 WHERE id = %s', (post_id,))
        message = '좋아요가 등록되었습니다.'
    
    cursor.close()
    conn.close()   
    flash(message)
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/delete/batch', methods=['POST'])
def delete_batch():
    post_ids = request.form.getlist('post_ids')
    
    if not post_ids:
        flash('삭제할 게시글을 선택해주세요.')
        return redirect(url_for('index'))
    
    conn = None
    try:
        conn = get_db_connection()
        # autocommit=True로 설정하면 매 실행마다 즉시 반영되어 위와 같은 트랜잭션 꼬임 에러를 방지합니다.
        conn.autocommit = True 
        cursor = conn.cursor()
        
        # 선택된 ID들을 정수형 리스트로 변환 (안정성 강화)
        ids_to_delete = [int(pid) for pid in post_ids]
        
        cursor.execute("DELETE FROM board.posts WHERE id = ANY(%s)", (ids_to_delete,))
        
        flash(f'{len(ids_to_delete)}개의 게시글이 성공적으로 삭제되었습니다.')
        
    except Exception as e:
        # 에러 발생 시 진행 중이던 트랜잭션을 취소하여 다음 요청에 영향이 없도록 함
        if conn:
            conn.rollback()
        print(f"Database Error: {e}") # 터미널에 실제 에러 출력
        flash(f'삭제 중 오류가 발생했습니다: {e}')
    finally:
        # 어떤 경우에도 연결은 반드시 닫아줍니다.
        if conn:
            conn.close()
            
    return redirect(url_for('index'))

@app.route('/fms')
def fms_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    # 1. 통계 요약 (전체 개체 수, 평균 난중 등)
    cursor.execute("SELECT count(*) as total, avg(egg_weight) as avg_weight FROM fms.chick_info")
    summary = cursor.fetchone()
    
    # 2. 품종별 개체 수 (그래프용)
    cursor.execute("SELECT breeds, count(*) as count FROM fms.chick_info GROUP BY breeds")
    breed_stats = cursor.fetchall()
    
    # 3. 최근 부화 데이터 (데이터 섹션용)
    cursor.execute("SELECT * FROM fms.chick_info ORDER BY hatchday DESC LIMIT 5")
    recent_chicks = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('fms_dashboard.html', 
                           summary=summary, 
                           breed_stats=breed_stats, 
                           recent_chicks=recent_chicks)

if __name__ == '__main__':
    app.run(debug=True)

