#include "DHT.h"
#include "WebSocketsClient.h"
#include "ESP8266WiFi.h"
#include "ESP8266WiFiMulti.h"
#include "ESP8266WebServer.h"
#include "ESP8266HTTPClient.h"

#define DHTTYPE DHT11
#define dht_pin 5
#define lm35_pin A0

String ID = "ESP1"; // 1 para prod 2 para prueba
const char* ssid = "VTR-4824546";
const char* pass = "mcJbpg7t4cgg";
String ip = "192.168.0.25";
String url = "http://"+ip+":8000/";
bool send = false;
DHT dht(dht_pin, DHTTYPE);

ESP8266WiFiMulti WiFiMulti;
WebSocketsClient webSocket;
ESP8266WebServer server(80);

int dht_temp;
int lm35_temp;
String wp;
String wd;
const long interval = 6000;
bool opt = true;

void setup(){
    dht.begin();
    Serial.begin(115200);
	WiFiMulti.addAP(ssid, pass);

	while(WiFiMulti.run() != WL_CONNECTED) {
		delay(100);
        Serial.print(".");
	}
    String query = "id="+ID+"&ip="+WiFi.localIP().toString();
    query += "&sens=dht11:lm35";
    query += "&dht11=Temperature:Celsius&lm35=Temperature:Celsius";

    webSocket.begin(ip, 8000, "/ws/board?"+query);
    
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);


    server.on("/data", dataHandler);
    server.on("/data/config", dataConfig);
    server.begin();

    dht_temp = dht.readTemperature();
    delay(2000);
    lm35_temp = readAnalogTemperature(lm35_pin);
    Serial.println(lm35_temp);
    Serial.println(dht_temp);
    delay(2000);
}

void loop(){
    webSocket.loop();
    server.handleClient();
    
    // Non Blocking timer
    static unsigned long currentMillis;
    if (millis() - currentMillis >= interval){
        // send on change data
        if (send){
            int dt = (int)dht.readTemperature();
            int lt = readAnalogTemperature(lm35_pin);
            String d;
            if (dht_temp != dt){
                dht_temp = dt;
                d = String(dt);
                webSocket.sendTXT("dht11:"+d);
            }
            if (lm35_temp != lt){
                lm35_temp = lt;
                d = String(lt);
                webSocket.sendTXT("lm35:"+d);
            }
        }
        currentMillis = millis();
    }
}

int readAnalogTemperature(int pin){
    int analogValue = analogRead(pin);
    float millivolts = (analogValue/1024.0) * 3300;
    int celsius = millivolts/10;
    return celsius;
}


void webSocketEvent(WStype_t type, uint8_t * payload, size_t length){
    switch (type){
    case WStype_CONNECTED:
        send = false;
        break;
    case WStype_DISCONNECTED:
        send = false;
        break;
    case WStype_TEXT:
        break;    
    default:
        break;
    }
}

void dataHandler(){
    int t;
    String sen;
    sen = server.arg("sensor");

    if (sen == "lm35")
        t = lm35_temp; //readAnalogTemperature(lm35_pin);
    if (sen == "dht11")
        t = dht_temp; //(int)dht.readTemperature();

    String st = String(t);

    server.send(200, "text/json",sen +":"+st);
}

void dataConfig(){
    String opt = server.arg("option");
    Serial.println(opt);
    if (opt == "sendoff"){
        send = false;
    }
    else if (opt == "sendon"){
        send = true;
    }
    server.send(200);
}
