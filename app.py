# app.py
import time#Jus to determine howlong the app takes to start / Enable reloader to know the  difference in the time takes to start
print("App starting at:", time.time())

from app import create_app

app = create_app()
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)#Remove the reloader later if necessary
