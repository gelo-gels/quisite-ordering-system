from src import init_db

app = init_db()

if __name__ == '__main__':
    app.run('0.0.0.0', debug=True, threaded=False)