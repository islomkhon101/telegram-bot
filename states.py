from aiogram.fsm.state import State, StatesGroup

class RegistrationForm(StatesGroup):
    full_name = State()
    phone = State()

class FlightForm(StatesGroup):
    date = State()
    custom_date = State()
    flight_no = State()
    airline = State()
    custom_airline = State()
    operation = State()
    route = State()
    stay_days = State()
    custom_stay_days = State()
    crew_hotel = State()
    pax_hotel = State()
    crew_count = State()
    pax_count = State()
    transfer = State()
    transfer_provider = State()
    catering = State()
    restaurant = State()
    custom_restaurant = State()
    extra_purchase = State()
    extra_purchase_text = State()
    served_mode = State()
    served_other = State()
    served_other_manual = State()
    served_together = State()
    served_together_manual = State()
    comment = State()
    photo_choice = State()
    photos = State()
    confirm = State()
    cancel_confirm = State()

class StatsForm(StatesGroup):
    start_date = State()
    end_date = State()

class DeleteForm(StatesGroup):
    flight_id = State()
