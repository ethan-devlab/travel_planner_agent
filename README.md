# Django Travel Planner
A Django project to build a travel planning platform.

## Install and Run
### For Windows:
```
python -m venv django_project
```
In the same directory, run the script in terminal
```
./django_project/Scripts/Activate
```
or run the following script in CMD instead
```
.\django_project\Scripts\Activate.bat
```
Make sure you have done the actions above to get into virtual environment, you will see something like `(django_project) C:\<Your Path>...` in your terminal or CMD.

Next, install the required packages.
```
cd traver_planner_agent
pip install -r requirements.txt
npm install
npm run build:css
```
Finally, run
```
python manage.py runserver
```
The default url will be `127.0.0.1:8000/`


### For Linux/macOS
```
python3 -m venv django_project
```
In the same directory, run the script in terminal
```
source ./django_project/bin/activate
```
Make sure you have done the actions above to get into virtual environment, you will see something like `(django_project) <Your Path>...%` in your terminal.

Next, install the required packages.
```
cd traver_planner_agent
pip install -r requirements.txt
npm install
npm run build:css
```
Finally, run
```
python manage.py runserver
```
The default url will be `127.0.0.1:8000/`
If port `8000` is already in use, run `python3 manage.py runserver 8001` instead.

### Environment Variables
Create a `.env` file in the `env` directory with the following content, replacing values as needed. There are example values in `env/.env.example` that you can copy and modify.

### SonarQube (Optional)
Configuration for SonarQube is included in `pyproject.example.toml`. To enable SonarQube analysis, copy this file to `pyproject.toml` and adjust the settings as needed.

---

## Account Info
* Admin: admin
* Password: 123

---

## Setting Route Locations

Route planning is available on the create and edit itinerary pages.

1. Add one location row for each stop in the trip.
2. Click or focus the location row you want to position.
3. Use the map search box to find a place, or click directly on the map to set that stop's coordinates.
4. Repeat for at least two stops. The route preview uses the visible order of the location rows.
5. Save the itinerary. The selected latitude, longitude, and route order are stored with each location.

If `ROUTING_SERVICE_URL` is not configured, the map still saves location markers, but route lines are not requested. Set `ROUTING_SERVICE_URL` to an OSRM-compatible service URL to enable route drawing.

## AI Itinerary Checks

The edit page can review the saved itinerary with four focuses: overall, stops, route, or budget. Unsaved form changes are intentionally excluded.

Route checks treat each location's transportation method as the incoming leg from the previous stop; the first stop's method is ignored. Car timing uses the configured OSRM driving service. Walking time is estimated from straight-line distance, while bus, train, HSR, plane, and boat legs are marked for manual schedule confirmation. Time-gap checks compare saved stop start times only and do not include time spent at each attraction.

Stop checks resolve city and country from saved coordinates with Nominatim. Results are cached for 90 days by default and public-service requests are throttled. Configure `NOMINATIM_BASE_URL`, `NOMINATIM_USER_AGENT`, `NOMINATIM_MIN_INTERVAL_SECONDS`, and `REVERSE_GEOCODE_CACHE_DAYS` for the deployment. Public Nominatim is intended only for moderate user-triggered use; larger deployments should use a hosted or self-managed provider.
