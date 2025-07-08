import React, { useState, useEffect, useRef } from "react";
import { parseDate } from "chrono-node";
import "./chatbot.css";

export default function Chatbot() {
  const chatboxRef = useRef(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const greetedRef = useRef(false);

  const [state, setState] = useState({
    intent: null,
    entities: {},
    pendingField: null,
    awaitingSlot: false,
    availableSlots: [],
    recommendations: [],
    recommendationsShown: false,
    cancelBookingIdsShown: false,
    awaitingOTP: false,
    sentSlot: null,
    otpPurpose: null,
  });

  const requiredFields = {
    booking: ["city", "cuisine", "restaurant_id", "date", "number_of_people", "contact_name", "contact_email", "contact_number"],
    cancel: ["contact_name", "contact_email", "contact_number", "booking_id"],
  };

  useEffect(() => {
    if (!greetedRef.current) {
      addMessage("🤖 Hello! I am your restaurant reservation assistant. How can I help you today?", "bot");
      greetedRef.current = true;
    }
  }, []);

  useEffect(() => {
    chatboxRef.current.scrollTop = chatboxRef.current.scrollHeight;
  }, [messages]);

  const addMessage = (text, sender) => {
    setMessages((prev) => [...prev, { text, sender }]);
  };

  const handleSend = () => {
    if (!input.trim()) return;
    addMessage(input, "user");
    const userInput = input.trim();
    setInput("");

    if (state.pendingField) {
      let userValue = userInput;

      if (state.pendingField === "date") {
        const parsed = parseDate(userValue);
        if (!parsed) {
          addMessage("❌ Couldn't understand the date. Try 'tomorrow', 'next Friday' etc.", "bot");
          return;
        }
        userValue = parsed.toISOString().split("T")[0];
      }

      if (state.pendingField === "restaurant_id") {
        const match = state.recommendations.find(
          (r) =>
            String(r.restaurant_id || r.id) === userValue ||
            r.name.toLowerCase() === userValue.toLowerCase()
        );
        if (!match) {
          addMessage("❌ Invalid restaurant name or ID. Please select from the above list.", "bot");
          return;
        }
        userValue = match.restaurant_id || match.id;
      }

      if (state.pendingField === "contact_email") {
        userValue = userValue.trim().replace(/\s+/g, "");
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(userValue)) {
          addMessage("❌ Please enter a valid email address (e.g., john@example.com).", "bot");
          return;
        }
      }

      const newEntities = { ...state.entities, [state.pendingField]: userValue };
      setState((prev) => ({ ...prev, entities: newEntities, pendingField: null }));
      setTimeout(() => continueFlow({ ...state, entities: newEntities, pendingField: null }), 100);
      return;
    }

    if (state.awaitingSlot) {
      const idx = parseInt(userInput) - 1;
      if (!isNaN(idx) && idx >= 0 && idx < state.availableSlots.length) {
        const chosenSlot = state.availableSlots[idx];
        setState((prev) => ({
          ...prev,
          awaitingSlot: false,
          sentSlot: chosenSlot,
          otpPurpose: "booking",
          awaitingOTP: true,
        }));
        sendOTP(state.entities.contact_email, "booking");
      } else {
        addMessage("❌ Invalid slot number. Please try again.", "bot");
      }
      return;
    }

    if (state.awaitingOTP) {
      if (userInput.toLowerCase() === "resend") {
        sendOTP(state.entities.contact_email, state.otpPurpose);
      } else {
        validateOTP(userInput);
      }
      return;
    }

    processInput(userInput);
  };

 const processInput = async (text) => {
  try {
    const response = await fetch("http://127.0.0.1:8000/intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_input: text }),
    });

    const data = await response.json();
    const detectedIntent = data.intent;
    const newEntities = typeof data.entities === "string" ? JSON.parse(data.entities) : data.entities;

    if (!detectedIntent) {
      addMessage("🤖 I couldn't understand that. Could you rephrase?", "bot");
      return;
    }

    if (detectedIntent === "greeting") {
      addMessage("👋 Hello! How can I assist you with your restaurant booking today?", "bot");
      return;
    }

    // If intent has changed from previous one → reset state
    if (state.intent && detectedIntent !== state.intent) {
      const newState = {
        intent: detectedIntent,
        entities: newEntities || {},
        pendingField: null,
        awaitingSlot: false,
        availableSlots: [],
        recommendations: [],
        recommendationsShown: false,
        cancelBookingIdsShown: false,
        awaitingOTP: false,
        sentSlot: null,
        otpPurpose: null,
      };
      setState(newState);
      addMessage("🔁 Got it! Switching to your new request...", "bot");
      continueFlow(newState);
    } else {
      // Same intent → merge entities and continue normally
      const mergedEntities = { ...state.entities, ...newEntities };
      const updatedState = {
        ...state,
        intent: detectedIntent,
        entities: mergedEntities,
      };
      setState(updatedState);
      continueFlow(updatedState);
    }
  } catch {
    addMessage("⚠️ Sorry, something went wrong while processing your input.", "bot");
  }
};


  const continueFlow = async (s) => {
    const intent = s.intent;
    const fields = requiredFields[intent] || [];

    if (intent === "booking") {
      const e = s.entities;
      if (e.city && e.cuisine && !e.restaurant_id && !state.recommendationsShown) {
        try {
          addMessage("🔍 Looking for recommendations...", "bot");
          const res = await fetch("http://127.0.0.1:8000/recommendations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_query: `${e.cuisine} restaurants in ${e.city}`,
              city: e.city,
              cuisine: e.cuisine,
            }),
          });
          const data = await res.json();

          if (!data.recommendations || data.recommendations.length === 0) {
            addMessage("😔 No recommendations found.", "bot");
            return;
          }

          data.recommendations.forEach((item, idx) => {
            addMessage(
              `${idx + 1}. ${item.name} (ID: ${item.restaurant_id || item.id}) - ${item.city}\nCuisine: ${item.cuisines?.join(", ") || item.cuisine}\nFeatures: ${item.features?.join(", ") || "N/A"}`,
              "bot"
            );
          });

          setState((prev) => ({
            ...prev,
            recommendations: data.recommendations,
            recommendationsShown: true,
            pendingField: "restaurant_id",
          }));
          addMessage("🏠 Please enter the restaurant name or ID from above:", "bot");
          return;
        } catch (err) {
          console.error("Recommendation error:", err);
          addMessage("⚠️ Failed to fetch recommendations.", "bot");
          return;
        }
      }
    }

    if (intent === "cancel") {
      const e = s.entities;
      const hasContact = e.contact_name && e.contact_email && e.contact_number;

      if (hasContact && !state.cancelBookingIdsShown) {
        try {
          addMessage("🔍 Fetching your bookings...", "bot");
          const res = await fetch("http://127.0.0.1:8000/bookings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(e),
          });
          const data = await res.json();

          if (data.bookings?.length) {
            let msg = "📝 Your bookings:\n";
            data.bookings.forEach((b, i) => {
              msg += `${i + 1}. Booking ID: ${b.booking_id}, Restaurant: ${b.name} (ID: ${b.restaurant_id}), Date: ${b.date}, Slot: ${b.time_slot}\n`;
            });
            addMessage(msg, "bot");

            setState((prev) => ({
              ...prev,
              cancelBookingIdsShown: true,
              pendingField: "booking_id",
            }));
            addMessage("🆔 Please enter your booking ID to cancel:", "bot");
          } else {
            addMessage("ℹ️ No bookings found with the provided details.", "bot");
            addMessage("🔁 Please re-enter your contact details to try again.", "bot");

            setTimeout(() => {
              setState((prev) => ({
                ...prev,
                cancelBookingIdsShown: false,
                entities: {
                  ...prev.entities,
                  contact_name: undefined,
                  contact_email: undefined,
                  contact_number: undefined,
                },
              }));
              continueFlow({
                ...s,
                entities: {
                  ...s.entities,
                  contact_name: undefined,
                  contact_email: undefined,
                  contact_number: undefined,
                },
              });
            }, 100);
          }

          return;
        } catch (err) {
          console.error(err);
          addMessage("⚠️ Failed to fetch bookings.", "bot");
          return;
        }
      }
    }

    for (let field of fields) {
      if (!s.entities[field]) {
        setState((prev) => ({ ...prev, pendingField: field }));
        const prompts = {
          city: "🌆 Which city are you in?",
          cuisine: "🍽️ What cuisine do you prefer?",
          restaurant_id: "🏠 Please enter the restaurant name or ID:",
          date: "📅 Please enter the booking date (e.g., 'tomorrow', 'next Monday'):",
          number_of_people: "👥 For how many people is the booking?",
          contact_name: "🧑 Please provide your full name:",
          contact_email: "📧 Please provide your email address:",
          contact_number: "📱 Please provide your contact number:",
          booking_id: "🆔 Please enter your booking ID to cancel:",
        };
        addMessage(prompts[field] || `Please provide ${field}.`, "bot");
        return;
      }
    }

    if (intent === "booking") {
      const payload = s.entities;
      fetch("http://127.0.0.1:8000/availability", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.available_slots || data.available_slots.length === 0) {
            addMessage("⚠️ No slots available. Try another date or restaurant.", "bot");
          } else {
            setState((prev) => ({
              ...prev,
              awaitingSlot: true,
              availableSlots: data.available_slots,
            }));
            addMessage("✅ Available slots:\n" + data.available_slots.map((s, i) => `${i + 1}. ${s}`).join("\n"), "bot");
            addMessage("🕒 Please enter the slot number you'd like to book:", "bot");
          }
        });
    }

    if (intent === "cancel") {
      setState((prev) => ({
        ...prev,
        awaitingOTP: true,
        otpPurpose: "cancellation",
      }));
      sendOTP(s.entities.contact_email, "cancellation");
    }
  };

  const sendOTP = async (email, purpose) => {
    try {
      const res = await fetch("http://127.0.0.1:8000/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, purpose }),
      });
      if (res.ok) {
        addMessage("📧 OTP sent to your email. Please enter it to proceed.", "bot");
      } else {
        addMessage("❌ Failed to send OTP.", "bot");
      }
    } catch {
      addMessage("❌ Error sending OTP.", "bot");
    }
  };

  const validateOTP = async (otp) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/validate-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        otp,
        email: state.entities.contact_email,
        ...state.entities,
        slot: state.sentSlot,
        purpose: state.otpPurpose,
      }),
    });
    const result = await res.json();

    if (res.ok && result.success) {
      addMessage("✅ OTP verified.", "bot");

      if (state.intent === "booking") {
        addMessage("📅 Proceeding with your booking...", "bot");
        finalizeBooking(); // booking handler
      } else if (state.intent === "cancel" || state.otpPurpose === "cancellation") {
        addMessage("🔁 Proceeding with cancellation...", "bot");
        cancelBooking(); // cancellation handler
      }

      // Reset OTP-related states
      setState((prev) => ({
        ...prev,
        awaitingOTP: false,
        otpPurpose: null,
      }));
    } else {
      addMessage(result.detail || "❌ OTP verification failed.", "bot");
    }
  } catch {
    addMessage("❌ OTP validation error.", "bot");
  }
};


  const finalizeBooking = async () => {
    const e = state.entities;
    const slot = state.sentSlot;
    const payload = {
      restaurant_id: e.restaurant_id,
      date: e.date,
      slot,
      number_of_people: e.number_of_people,
      contact_name: e.contact_name,
      contact_email: e.contact_email,
      contact_number: e.contact_number,
    };

    try {
      const res = await fetch("http://127.0.0.1:8000/book", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (data.success) {
        addMessage(`✅ Booking successful! Your booking ID is ${data.booking_id}.`, "bot");
        addMessage("📩 A confirmation email has been sent. How can I assist you further?", "bot");
      } else {
        addMessage("❌ Booking failed: " + (data.message || "Unknown error."), "bot");
      }
    } catch (err) {
      console.error("❌ Booking request failed:", err);
      addMessage("❌ Booking request failed. Please try again later.", "bot");
    }

    setState({
      intent: null,
      entities: {},
      pendingField: null,
      awaitingSlot: false,
      availableSlots: [],
      recommendations: [],
      recommendationsShown: false,
      cancelBookingIdsShown: false,
      awaitingOTP: false,
      sentSlot: null,
      otpPurpose: null,
    });
  };

  const cancelBooking = async () => {
  const e = state.entities;

  if (!e.booking_id) {
    addMessage("🆔 Please enter your booking ID to cancel:", "bot");
    setState((prev) => ({
      ...prev,
      pendingField: "booking_id",
    }));
    return;
  }

  addMessage("⏳ Cancelling your booking...", "bot");

  try {
    const res = await fetch("http://127.0.0.1:8000/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        booking_id: e.booking_id,
        contact_name: e.contact_name,
        contact_email: e.contact_email,
        contact_number: e.contact_number,
      }),
    });

    const data = await res.json();

    if (data.success) {
      addMessage("✅ Booking cancelled successfully.", "bot");
      addMessage("📩 A cancellation confirmation has been sent to your email. Let me know if you need further assistance.", "bot");
    } else {
      addMessage("❌ Cancellation failed. Please check your booking ID and try again.", "bot");
    }
  } catch (err) {
    console.error("Cancellation error:", err);
    addMessage("⚠️ Cancellation request failed. Please try again later.", "bot");
  }

  setState({
    intent: null,
    entities: {},
    pendingField: null,
    awaitingSlot: false,
    availableSlots: [],
    recommendations: [],
    recommendationsShown: false,
    cancelBookingIdsShown: false,
    awaitingOTP: false,
    sentSlot: null,
    otpPurpose: null,
  });
};

  return (
    <div>
      <div id="chatbox" ref={chatboxRef}>
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.sender}`}>{msg.text}</div>
        ))}
      </div>
      <div id="inputArea">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Type a message..."
        />
        <button onClick={handleSend}>Send</button>
      </div>
    </div>
  );
}
