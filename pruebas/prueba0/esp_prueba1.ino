#include "DHT.h"
#include "WebSocketsClient.h"
#include "ESP8266WiFi.h"
#include "ESP8266WiFiMulti.h"
#include "ESP8266WebServer.h"

#define DHTTYPE DHT11
#define dht_dpin D4

String ID = "ESP01";
const char* ssid = "VTR-4824546";
const char* pass = "mcJbpg7t4cgg";

DHT dht(5, DHTTYPE);
ESP8266WiFiMulti WiFiMulti;
WebSocketsClient webSocket;
ESP8266WebServer server(80);

float temp;
float humi;
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

    webSocket.begin("192.168.0.15", 8000, "/ws?id="+ID);
    
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);

    server.on("/data", dataHandler);

    server.begin();
    Serial.println("ready");
    
    temp = dht.readTemperature();
    delay(2000);
    humi = dht.readHumidity();
    delay(2000);
}

void loop(){
    webSocket.loop();
    server.handleClient();
    
    // Non Blocking timer
    static unsigned long currentMillis;
    if (millis() - currentMillis >= interval){
        // send on change data
        if (opt){
            float t = dht.readTemperature();
            if (temp != t){
                Serial.println(t);
                temp = t;
                String d = String(t);
                webSocket.sendTXT("c:t:"+d);
            }
            opt = false;
        }
        else{
            float h = dht.readHumidity();    
            if (humi != h){
                Serial.println(h);
                humi = h;
                String d = String(h);
                webSocket.sendTXT("c:h:"+d);
            }
            opt = true;
        }
            
        currentMillis = millis();
    }
}


void webSocketEvent(WStype_t type, uint8_t * payload, size_t length){
    switch (type){
    case WStype_CONNECTED:
        break;
    case WStype_DISCONNECTED:
        break;
    case WStype_TEXT:
        break;    
    default:
        break;
    }
}

void dataHandler(){
    float t = temp;
    float h = humi;

    String st = String(t);
    String sh = String(h);

    Serial.println("ok");
    server.send(200, "text/json","t:"+st+":h:"+sh+":id:"+ID);
}
