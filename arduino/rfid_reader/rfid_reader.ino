// Smart Attendance - RFID reader (Arduino Uno + RC522)
// Wiring: SDA->10, SCK->13, MOSI->11, MISO->12, RST->9, GND->GND, 3.3V->3.3V
#include <SPI.h>
#include <MFRC522.h>

MFRC522 rfid(10, 9);  // SS, RST

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  Serial.println(uid);   // e.g. A3F29C1B

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1500);           // prevent double reads
}
