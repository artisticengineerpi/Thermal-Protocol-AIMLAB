/*
 * AIMLAB - combined Arduino Uno BENCH TEST, Serial Monitor at 115200 baud.
 * Line ending: Newline or Both NL & CR. Commands are case insensitive.
 *
 * L298N: D9 -> ENA (remove ENA jumper), D8 -> IN1, D7 -> IN2.
 * Peltier -> OUT1/OUT2. Motors M0..M3 -> drivers on D5,D6,D3,D11.
 * Never power motors/Peltier directly from an Arduino pin.
 * Fit the Peltier heatsink and fan. Start with low PWM on the bench.
 * No temperature sensors are read by this sketch. Timers are NOT thermal
 * protection and cannot protect against a frozen MCU or failed driver.
 * HOT/COLD are electrical polarity names: verify the actual contact face.
 * This is a manual test interface, not the existing PC experiment protocol.
 */
#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

const uint8_t PELTIER_EN = 9;
const uint8_t PELTIER_IN1 = 8;
const uint8_t PELTIER_IN2 = 7;
const uint8_t MOTOR_PINS[4] = {5, 6, 3, 11};
const uint8_t DEFAULT_PWM = 255;      // Full duty by default.
const unsigned long DEFAULT_MS = 1000;
const unsigned long MAX_PELTIER_MS = 5000; // Per polarity, including settling.
const unsigned long MAX_MOTOR_MS = 10000;
const unsigned long REVERSAL_PAUSE_MS = 1000;
const unsigned long SETTLE_MS = 50;   // Output disabled before applying power.
const unsigned long SWEEP_UPDATE_MS = 20;

enum TestMode { IDLE, THERMAL_SINGLE, THERMAL_PAIR, MOTOR_SINGLE, MOTOR_SWEEP, PROTOCOL_TRIAL };
TestMode mode = IDLE;
uint8_t requestedPwm = 0;
uint8_t livePeltierPwm = 0;
uint8_t liveMotorPwm[4] = {0, 0, 0, 0};
bool repeatSweep = false;
unsigned long protocolLeadMs = 0;
unsigned long protocolDurationMs = 5000;
char protocolCondition = 'A';
uint8_t protocolMotorPwm[4] = {83,83,83,83};
unsigned long thermalSettleStart = 0;
unsigned long lastHeartbeat = 0;
const unsigned long PROTOCOL_MS = 5000;
const unsigned long HEARTBEAT_TIMEOUT_MS = 750;
bool hotPolarity = true;
bool thermalPowered = false;
uint8_t phase = 0;
unsigned long phaseStart = 0;
unsigned long durationMs = 0;
unsigned long lastSweepUpdate = 0;
char lineBuffer[80];
uint8_t lineLength = 0;
bool discardLine = false;
char receivedLine[80];

void peltierOff() {
  analogWrite(PELTIER_EN, 0);
  digitalWrite(PELTIER_IN1, LOW);
  digitalWrite(PELTIER_IN2, LOW);
  livePeltierPwm = 0;
  thermalPowered = false;
}

void motorsOff() {
  for (uint8_t i = 0; i < 4; ++i) {
    analogWrite(MOTOR_PINS[i], 0);
    liveMotorPwm[i] = 0;
  }
}

void stopAll() {
  peltierOff();
  motorsOff();
  mode = IDLE;
  repeatSweep = false;
  phase = 0;
}

void finishTest() {
  stopAll();
  Serial.println(F("DONE: all outputs OFF"));
}

void setThermalPolarity(bool hot) {
  peltierOff();
  hotPolarity = hot;
  phaseStart = millis();
  // Direction pins and enable are applied after SETTLE_MS in loop().
}

void applyThermalPower() {
  // Polarity reversed for the user-flipped Peltier orientation.
  digitalWrite(PELTIER_IN1, hotPolarity ? HIGH : LOW);
  digitalWrite(PELTIER_IN2, hotPolarity ? LOW : HIGH);
  analogWrite(PELTIER_EN, requestedPwm);
  livePeltierPwm = requestedPwm;
  thermalPowered = true;
}

void printHelp() {
  Serial.println(F("\nAIMLAB TEST v7.0 - 115200 baud, Newline"));
  Serial.println(F("1 / 2 / 3 / 4            Motor 1 / 2 / 3 / 4: PWM 255, 1 second"));
  Serial.println(F("5                        Stop ALL outputs"));
  Serial.println(F("6                        Peltier HOT: PWM 255, 1 second"));
  Serial.println(F("7                        Peltier COLD: PWM 255, 1 second"));
  Serial.println(F("8                        Peltier HOT -> OFF -> COLD"));
  Serial.println(F("9                        Repeat motor sweep until 5 (STOP)"));
  Serial.println(F("RUN A..H H|C thermalPWM m1 m2 m3 m4: 5s GUI trial"));
  Serial.println(F("SET H|C thermalPWM m1 m2 m3 m4: live levels; E..H = single motors"));
  Serial.println(F("GUI requires PING every 250ms; 750ms link-loss shutdown."));
  Serial.println(F("HELP                     Show commands"));
  Serial.println(F("STATUS                   Output state"));
  Serial.println(F("STOP or OFF              Stop ALL outputs"));
  Serial.println(F("!                        Immediate stop; no Enter needed"));
  Serial.println(F("HOT [pwm] [ms]           One thermal polarity"));
  Serial.println(F("COLD [pwm] [ms]          Opposite thermal polarity"));
  Serial.println(F("PELTIER [pwm] [ms]       HOT -> OFF 1s -> COLD -> OFF"));
  Serial.println(F("MOTOR n [pwm] [ms]       Test one motor, n = 0..3"));
  Serial.println(F("SWEEP [pwm] [ms]         M0 -> M3 -> M0; ms per leg"));
  Serial.println(F("PWM 0..255; default 255. Default duration 1000 ms."));
  Serial.println(F("Thermal: 100..5000 ms/phase. Motor: 100..10000 ms."));
  Serial.println(F("Sweep: 200..10000 ms/leg; default 3000 ms/leg."));
  Serial.println(F("Each new test stops the previous test first."));
  Serial.println(F("No temperature feedback. Bench test only; verify driver wiring."));
  Serial.println(F("Examples: HOT 255 1000 | MOTOR 0 255 2000 | SWEEP 255 3000"));
}

void printStatus() {
  Serial.print(F("Mode: "));
  switch (mode) {
    case IDLE: Serial.print(F("IDLE")); break;
    case THERMAL_SINGLE: Serial.print(F("THERMAL")); break;
    case THERMAL_PAIR: Serial.print(F("PELTIER PAIR")); break;
    case MOTOR_SINGLE: Serial.print(F("SINGLE MOTOR")); break;
    case MOTOR_SWEEP: Serial.print(F("SWEEP")); break;
    case PROTOCOL_TRIAL: Serial.print(F("PROTOCOL")); break;
  }
  Serial.print(F(" | Peltier PWM=")); Serial.print(livePeltierPwm);
  Serial.print(F(" polarity=")); Serial.print(hotPolarity ? F("HOT") : F("COLD"));
  Serial.print(F(" | Motors PWM="));
  for (uint8_t i = 0; i < 4; ++i) {
    if (i) Serial.print(',');
    Serial.print(liveMotorPwm[i]);
  }
  Serial.println();
}

// Strict unsigned decimal parser: reject negatives, trailing junk and overflow.
bool parseNumber(const char *s, unsigned long low, unsigned long high,
                 unsigned long &value) {
  if (!s || !*s) return false;
  value = 0;
  for (; *s; ++s) {
    if (*s < '0' || *s > '9') return false;
    const uint8_t digit = *s - '0';
    if (value > high / 10 || (value == high / 10 && digit > high % 10)) return false;
    value = value * 10 + digit;
  }
  return value >= low;
}

void badCommand() {
  stopAll();
  Serial.print(F("ERROR received: ["));
  Serial.print(receivedLine);
  Serial.println(F("]; all outputs OFF."));
  Serial.println(F("Use 6=HOT, 7=COLD, 8=BOTH, 5=STOP. Send one command, with Newline."));
}

void handleLine(char *line) {
  // Retain the actual input before strtok replaces separators with NUL bytes.
  strncpy(receivedLine, line, sizeof(receivedLine) - 1);
  receivedLine[sizeof(receivedLine) - 1] = '\0';
  // Pasted text can contain UTF-8 non-breaking spaces. Normalize only known
  // whitespace, never discard arbitrary characters that could change a command.
  char *read = line, *write = line;
  while (*read) {
    const unsigned char c = (unsigned char)*read;
    if (c == 0xC2 && (unsigned char)read[1] == 0xA0) {
      *write++ = ' '; read += 2;
    } else if (c == 0xE2 && (unsigned char)read[1] == 0x80 &&
               (unsigned char)read[2] == 0xAF) {
      *write++ = ' '; read += 3;
    } else {
      *write++ = isspace(c) ? ' ' : *read;
      ++read;
    }
  }
  *write = '\0';
  char *args[10];
  uint8_t count = 0;
  char *token = strtok(line, " \t");
  while (token) {
    if (count == 10) { badCommand(); return; }
    args[count++] = token;
    token = strtok(NULL, " \t");
  }
  if (!count) return;
  for (char *p = args[0]; *p; ++p) *p = toupper((unsigned char)*p);
  const char *cmd = args[0];
  const bool continuousSweep = count == 1 && !strcmp(cmd, "9");
  if (!strcmp(cmd, "IDENTIFY") && count == 1) {
    Serial.println(F("AIMLAB_COMBINED_V7")); return;
  }
  if (!strcmp(cmd, "PING") && count == 1) {
    lastHeartbeat = millis(); Serial.println(F("PONG")); return;
  }
  if (!strcmp(cmd, "SET")) {
    unsigned long values[5];
    if (count != 7 || strlen(args[1]) != 1 || (args[1][0] != 'H' && args[1][0] != 'C')) { badCommand(); return; }
    for (uint8_t i=0;i<5;++i) if (!parseNumber(args[i+2],0,255,values[i])) { badCommand(); return; }
    if (mode != IDLE && mode != PROTOCOL_TRIAL) { stopAll(); Serial.println(F("FAULT BUSY")); return; }
    const bool newHot = args[1][0] == 'H';
    if (newHot != hotPolarity) { peltierOff(); hotPolarity = newHot; thermalSettleStart = millis(); }
    requestedPwm = (uint8_t)values[0];
    for(uint8_t i=0;i<4;++i) protocolMotorPwm[i]=(uint8_t)values[i+1];
    if (thermalPowered) { analogWrite(PELTIER_EN,requestedPwm); livePeltierPwm=requestedPwm; }
    lastSweepUpdate = millis() - SWEEP_UPDATE_MS;
    Serial.println(F("ACK SET")); return;
  }
  if (!strcmp(cmd, "RUN")) {
    unsigned long values[5];
    if ((count != 5 && count != 8 && count != 9 && count != 10) || strlen(args[1]) != 1 || args[1][0] < 'A' || args[1][0] > 'H' ||
        strlen(args[2]) != 1 || (args[2][0] != 'H' && args[2][0] != 'C')) { badCommand(); return; }
    const uint8_t supplied = count == 5 ? 2 : 5;
    for(uint8_t i=0;i<supplied;++i) if (!parseNumber(args[i+3],0,255,values[i])) { badCommand(); return; }
    unsigned long lead = 0;
    if (count >= 9 && !parseNumber(args[8],0,2000,lead)) { badCommand(); return; }
    if (mode != IDLE) { stopAll(); Serial.println(F("FAULT BUSY")); return; }
    unsigned long motionMs = 5000;
    if (count == 10 && (!parseNumber(args[9],1000,8000,motionMs) || motionMs % 100 != 0)) { badCommand(); return; }
    protocolDurationMs = (args[1][0] == 'C' || args[1][0] == 'D') ? motionMs : PROTOCOL_MS;
    protocolLeadMs = args[1][0] == 'D' ? lead : 0;
    stopAll(); protocolCondition = args[1][0];
    for(uint8_t i=0;i<4;++i) protocolMotorPwm[i]=(uint8_t)values[count==5?1:i+1];
    requestedPwm=(uint8_t)values[0]; hotPolarity=args[2][0]=='H';
    phaseStart=millis(); thermalSettleStart=phaseStart; lastHeartbeat=phaseStart;
    lastSweepUpdate=phaseStart-SWEEP_UPDATE_MS; mode=PROTOCOL_TRIAL;
    Serial.print(F("ACK RUN ")); Serial.println(protocolCondition); return;
  }
  // Number shortcuts for thermal tests use the same validated test path.
  if (count == 1 && cmd[1] == '\0') {
    if (cmd[0] == '6') cmd = "HOT";
    else if (cmd[0] == '7') cmd = "COLD";
    else if (cmd[0] == '8') cmd = "PELTIER";
    else if (cmd[0] == '9') cmd = "SWEEP";
  }
  // Simple one-based motor shortcuts; named MOTOR still uses indices 0..3.
  if (count == 1 && cmd[1] == '\0' && cmd[0] >= '1' && cmd[0] <= '5') {
    if (cmd[0] == '5') {
      stopAll();
      Serial.println(F("STOPPED: all outputs OFF"));
      return;
    }
    const uint8_t motorIndex = cmd[0] - '1';
    stopAll();
    requestedPwm = DEFAULT_PWM;
    durationMs = DEFAULT_MS;
    Serial.print(F("START motor ")); Serial.print(motorIndex + 1);
    Serial.println(F(" PWM=255, duration=1000 ms"));
    phaseStart = millis();
    mode = MOTOR_SINGLE;
    analogWrite(MOTOR_PINS[motorIndex], requestedPwm);
    liveMotorPwm[motorIndex] = requestedPwm;
    return;
  }
  if (!strcmp(cmd, "STOP") || !strcmp(cmd, "OFF")) {
    stopAll(); Serial.println(F("STOPPED: all outputs OFF")); return;
  }
  if (!strcmp(cmd, "HELP") && count == 1) {
    // Long help output is printed only after outputs are disabled.
    stopAll(); printHelp(); return;
  }
  if (!strcmp(cmd, "STATUS") && count == 1) { printStatus(); return; }

  const bool motor = !strcmp(cmd, "MOTOR");
  const bool sweep = !strcmp(cmd, "SWEEP");
  const bool hot = !strcmp(cmd, "HOT");
  const bool cold = !strcmp(cmd, "COLD");
  const bool pair = !strcmp(cmd, "PELTIER");
  if (!(motor || sweep || hot || cold || pair)) { badCommand(); return; }
  unsigned long motorIndex = 0, pwm = DEFAULT_PWM;
  unsigned long ms = sweep ? 3000UL : DEFAULT_MS;
  const uint8_t first = motor ? 2 : 1;
  if (count > first + 2 || (motor && (count < 2 || !parseNumber(args[1], 0, 3, motorIndex)))) {
    badCommand(); return;
  }
  if (count > first && !parseNumber(args[first], 0, 255, pwm)) { badCommand(); return; }
  const unsigned long maximum = (motor || sweep) ? MAX_MOTOR_MS : MAX_PELTIER_MS;
  if (count > first + 1 && !parseNumber(args[first + 1], sweep ? 200 : 100, maximum, ms)) {
    badCommand(); return;
  }

  stopAll();
  requestedPwm = (uint8_t)pwm;
  durationMs = ms;
  Serial.print(F("START ")); Serial.print(cmd);
  Serial.print(F(" PWM=")); Serial.print(pwm);
  Serial.print(F(" phase_ms=")); Serial.println(ms);
  phaseStart = millis();
  if (motor) {
    mode = MOTOR_SINGLE;
    analogWrite(MOTOR_PINS[motorIndex], requestedPwm);
    liveMotorPwm[motorIndex] = requestedPwm;
  } else if (sweep) {
    mode = MOTOR_SWEEP;
    repeatSweep = continuousSweep;
    if (repeatSweep) Serial.println(F("REPEATING: send 5 to stop"));
    lastSweepUpdate = phaseStart - SWEEP_UPDATE_MS;
  } else {
    mode = pair ? THERMAL_PAIR : THERMAL_SINGLE;
    setThermalPolarity(!cold);
  }
}

void updateTest() {
  const unsigned long now = millis();
  const unsigned long elapsed = now - phaseStart; // Handles millis rollover.
  if (mode == PROTOCOL_TRIAL) {
    if (now - lastHeartbeat >= HEARTBEAT_TIMEOUT_MS) {
      stopAll(); Serial.println(F("FAULT HEARTBEAT")); return;
    }
    if (elapsed >= protocolDurationMs + protocolLeadMs) {
      const char completed = protocolCondition;
      stopAll(); Serial.print(F("DONE RUN ")); Serial.println(completed); return;
    }
    // Combined heating includes the lead and ends with the complete motor stroke.
    // Thermal-only keeps its existing five-second window.
    const unsigned long thermalMs = protocolCondition == 'D'
      ? protocolLeadMs + protocolDurationMs : PROTOCOL_MS;
    if (elapsed >= thermalMs) peltierOff();
    if (elapsed < thermalMs && (protocolCondition == 'B' || protocolCondition == 'D') &&
        !thermalPowered && now - thermalSettleStart >= SETTLE_MS) applyThermalPower();
    if (protocolCondition >= 'E') {
      for(uint8_t i=0;i<4;++i) {
        const uint8_t value = i == protocolCondition-'E' ? protocolMotorPwm[i] : 0;
        analogWrite(MOTOR_PINS[i],value);liveMotorPwm[i]=value;
      }
    }
    if (elapsed >= protocolLeadMs && (protocolCondition == 'C' || protocolCondition == 'D') &&
        now - lastSweepUpdate >= SWEEP_UPDATE_MS) {
      lastSweepUpdate = now;
      // Equal shifted envelopes: 2 s each, 1 s SOA; last motor ends at 5 s.
      for (uint8_t i = 0; i < 4; ++i) {
        const unsigned long soa = protocolDurationMs / 5;
        const unsigned long ramp = protocolDurationMs / 10;
        const unsigned long envelope = 2 * soa;
        const unsigned long onset = protocolLeadMs + i * soa;
        float level = 0.0f;
        if (elapsed >= onset && elapsed < onset + envelope) {
          const unsigned long local = elapsed - onset;
          level = local < ramp ? (float)local / ramp :
                  local <= envelope - ramp ? 1.0f : (float)(envelope - local) / ramp;
        }
        const uint8_t value = (uint8_t)(protocolMotorPwm[i] * level + 0.5f);
        analogWrite(MOTOR_PINS[i], value); liveMotorPwm[i] = value;
      }
    }
    return;
  }
  if (mode == THERMAL_SINGLE || mode == THERMAL_PAIR) {
    if (mode == THERMAL_PAIR && phase == 1) {
      if (elapsed >= REVERSAL_PAUSE_MS) {
        phase = 2;
        setThermalPolarity(false);
        Serial.println(F("PHASE: COLD polarity"));
      }
      return;
    }
    if (elapsed >= durationMs) {
      peltierOff();
      if (mode == THERMAL_PAIR && phase == 0) {
        phase = 1;
        phaseStart = now;
        Serial.println(F("PHASE: OFF, reversal pause 1000 ms"));
      } else finishTest();
    } else if (!thermalPowered && elapsed >= SETTLE_MS) {
      applyThermalPower();
    }
  } else if (mode == MOTOR_SINGLE) {
    if (elapsed >= durationMs) finishTest();
  } else if (mode == MOTOR_SWEEP) {
    const unsigned long cycleMs = 2UL * durationMs;
    unsigned long sweepElapsed = elapsed;
    if (elapsed >= cycleMs) {
      if (!repeatSweep) { finishTest(); return; }
      sweepElapsed = elapsed % cycleMs;
      // Rebase every cycle so indefinite operation survives millis rollover.
      phaseStart = now - sweepElapsed;
    }
    if (now - lastSweepUpdate < SWEEP_UPDATE_MS) return;
    lastSweepUpdate = now;
    // Linear crossfade between adjacent motors, forward then reverse.
    const float leg = sweepElapsed <= durationMs ? sweepElapsed : cycleMs - sweepElapsed;
    const float position = 3.0f * leg / durationMs;
    for (uint8_t i = 0; i < 4; ++i) {
      float distance = position - i;
      if (distance < 0) distance = -distance;
      const uint8_t value = distance >= 1.0f ? 0 : (uint8_t)(requestedPwm * (1.0f - distance) + 0.5f);
      analogWrite(MOTOR_PINS[i], value);
      liveMotorPwm[i] = value;
    }
  }
}

void setup() {
  // Preload LOW output latches before changing pin direction.
  digitalWrite(PELTIER_EN, LOW); pinMode(PELTIER_EN, OUTPUT);
  digitalWrite(PELTIER_IN1, LOW); pinMode(PELTIER_IN1, OUTPUT);
  digitalWrite(PELTIER_IN2, LOW); pinMode(PELTIER_IN2, OUTPUT);
  for (uint8_t i = 0; i < 4; ++i) {
    digitalWrite(MOTOR_PINS[i], LOW); pinMode(MOTOR_PINS[i], OUTPUT);
  }
  stopAll();
  Serial.begin(115200);
  printHelp();
}

void loop() {
  updateTest();
  // Bound serial processing so a continuous input stream cannot starve timers.
  for (uint8_t budget = 0; budget < 16 && Serial.available(); ++budget) {
    const char c = (char)Serial.read();
    if (c == '!') {
      stopAll();
      lineLength = 0;
      discardLine = true; // Drop remaining characters of the interrupted line.
      Serial.println(F("EMERGENCY STOP: all outputs OFF"));
    } else if (c == '\n' || c == '\r') {
      if (!discardLine && lineLength) {
        lineBuffer[lineLength] = '\0';
        handleLine(lineBuffer);
      }
      lineLength = 0;
      discardLine = false;
    } else if (!discardLine) {
      if (lineLength < sizeof(lineBuffer) - 1) lineBuffer[lineLength++] = c;
      else {
        stopAll(); lineLength = 0; discardLine = true;
        Serial.println(F("ERROR: line too long; all outputs OFF"));
      }
    }
    updateTest();
  }
}





