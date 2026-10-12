# Go

**Status:** 🚀 **Launched**

<p align="center">
  <img src="apps/mobile/assets/icon.png" alt="Go app icon" width="120" />
</p>

iOS commitment device that charges you when you're late.

**Live:** https://go-place.vercel.app

---

## 🎯 The Problem

Being late is:
- A habit, not a series of accidents
- Often tolerated without real consequences
- Hard to change through willpower alone
- Disrespectful to others' time

Traditional reminders don't work because there's no cost to ignoring them.

---

## 💡 The Solution

**Go** makes lateness expensive by combining:
- Calendar integration
- GPS location tracking
- Walking ETA calculation
- Geofenced arrival detection
- Stripe penalty charges

### How It Works

```
Calendar event detected
         ↓
Geocode destination address
         ↓
Calculate walking ETA from current GPS
         ↓
Send "leave now" push notification
         ↓
Monitor GPS → Check destination geofence
         ↓
    Arrived on time?
    ├─ Yes → No charge
    └─ No  → Stripe charge to your own card
```

---

## ✨ Features

### Automatic Event Processing
- Reads Google Calendar
- Extracts event locations
- Geocodes addresses to coordinates

### Smart ETA
- Current GPS position
- Walking route calculation
- Real-time "leave now" notifications

### Geofence Detection
- Arrival confirmation via GPS
- Grace period buffer
- Automatic check-in

### Financial Commitment
- Stripe integration
- Charges your own card
- 7-day payment method lockup (anti-escape)

### Commitment Design
Removing a payment method takes **7 days** to process. You can't easily escape the system once you're committed.

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Mobile** | iOS (Swift, SwiftUI) |
| **Web** | Next.js landing page |
| **Calendar** | Google Calendar API |
| **Location** | CoreLocation (iOS) |
| **Geofencing** | CLLocationManager regions |
| **Payments** | Stripe API |
| **Geocoding** | MapKit / Google Maps API |
| **Backend** | API routes for Stripe/calendar |
| **Deployment** | Vercel (web), TestFlight (iOS) |

---

## 🧠 The Psychology

**Commitment devices work** when:
1. The cost is real (actual money, not points)
2. Escape is difficult (7-day lockup)
3. Consequences are immediate (charge fires same day)
4. You chose this (self-imposed system)

**Go** isn't a reminder app — it's a behavioral commitment tool.

---

## 🎯 Use Cases

**Chronic lateness:** Breaking the habit through financial accountability  
**Important meetings:** Ensuring you're never late to high-stakes events  
**Accountability:** When shame isn't enough  
**Behavioral change:** Using loss aversion as a motivator

---

## 🚀 What This Demonstrates

- **iOS development:** Swift, SwiftUI, CoreLocation, geofencing
- **API integration:** Google Calendar, Stripe, geocoding
- **Product design:** Commitment device theory, anti-escape mechanisms
- **Full-stack:** iOS + web + backend
- **UX psychology:** Loss aversion, behavioral economics

---

## 🔐 Privacy & Safety

- Location only tracked near event times
- Payment only charged for confirmed lateness
- User controls penalty amount
- Can disable for emergencies (with 7-day delay)

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app

---

**Original working title:** Class on Time  
**Production name:** Go
