# Noor Clinic Patient Tracker

A Flask-based patient tracking application that allows you to search for patients and visualize their A1c levels over time.

## Features

- 🔍 **Patient Search**: Search by patient ID or city
- 📊 **A1c Tracking**: View A1c measurements over time with interactive graphs
- 📈 **Trend Analysis**: Interactive Plotly charts showing patient progress
- 👥 **Patient Dashboard**: Browse active patients at a glance
- 🎯 **Target Goals**: Visual indication of A1c targets (7% for most diabetics)

## Setup

### Prerequisites

- Python 3.8+

### Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Import patient data:**
   ```bash
   python import_data.py
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

   The app will be available at: `http://localhost:5000`

## Usage

- **Search**: Use the main search bar to find patients by ID or location
- **View Details**: Click on any patient card to see their detailed profile
- **Analyze Trends**: View interactive A1c trend graphs with target markers
- **Dashboard**: Browse recently active patients on the homepage

## Database Schema

### Patients Table
- `patient_id` - Unique identifier
- `patient_identifier` - Patient number/code from data source
- `sex` - Patient gender
- `age_at_registration` - Age at data collection
- `city, state, postal_code` - Location information
- `most_recent_visit_date` - Last visit date
- `active` - Whether patient is currently active
- `fake` - Data quality flag

### Lab Observations Table
- `observation_id` - Unique identifier
- `patient_id` - Reference to patient
- `lab_observation_code` - Lab test code
- `lab_observation_description` - Test description (e.g., HEMOGLOBIN A1c)
- `lab_observation_value` - Test result value
- `lab_observation_unit` - Unit of measurement
- `observation_datetime` - Date/time of test

## API Endpoints

### Search
- `GET /api/search?q=<query>&limit=<limit>` - Search patients

### Patient Data
- `GET /api/patient/<patient_id>` - Get patient details
- `GET /api/patient/<patient_id>/a1c-graph` - Get A1c trend graph data
- `GET /api/patients/all-active?limit=<limit>` - Get active patients

## Technologies

- **Backend**: Flask, SQLAlchemy
- **Database**: PostgreSQL
- **Frontend**: HTML, CSS, JavaScript
- **Charting**: Plotly.js
- **Data Processing**: Pandas

## Notes

- A1c target of 9% is used as default, configurable in chart code
- Values like ">14.0" are automatically cleaned and converted to numeric values
- Database includes indices on frequently queried columns for performance

## Future Enhancements

- User authentication and role-based access
- Export patient data to CSV/PDF
- Multiple lab metrics tracking (not just A1c)
- Predictive analytics for patient outcomes
- Mobile app interface
- Alert system for out-of-range values
