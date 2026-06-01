(function () {
  const DEFAULT_CENTER = [25.0375, 121.5637];
  const NOMINATIM_SEARCH_URL = 'https://nominatim.openstreetmap.org/search';
  const NOMINATIM_MIN_INTERVAL_MS = 1100;
  const geocodeCache = new Map();
  let geocodeQueue = Promise.resolve();
  let nextGeocodeAt = 0;

  function getEntries() {
    return Array.from(document.querySelectorAll('[data-location-entry]'));
  }

  function entryName(entry) {
    const input = entry.querySelector('[name="location_name[]"]');
    return input?.value.trim() ? input.value.trim() : '地點';
  }

  function markerLabelElement(text) {
    const element = document.createElement('span');
    element.textContent = text;
    return element;
  }

  function readCoordinate(input) {
    const value = Number.parseFloat(input.value);
    return Number.isFinite(value) ? value : null;
  }

  function setExpenseNames() {
    getEntries().forEach((entry, index) => {
      entry.querySelectorAll('[data-expense-type]').forEach((field) => {
        field.name = `expense_type_${index}[]`;
      });
      entry.querySelectorAll('[data-expense-amount]').forEach((field) => {
        field.name = `expense_amount_${index}[]`;
      });
    });
  }

  function setRouteOrders() {
    getEntries().forEach((entry, index) => {
      const order = entry.querySelector('[name="route_order[]"]');
      if (order) order.value = index;
    });
  }

  function updateLocationOrderControls() {
    const entries = getEntries();
    entries.forEach((entry, index) => {
      const moveUp = entry.querySelector('[data-location-move="up"]');
      const moveDown = entry.querySelector('[data-location-move="down"]');
      if (moveUp) moveUp.disabled = index === 0;
      if (moveDown) moveDown.disabled = index === entries.length - 1;
    });
  }

  function setEntryCoordinate(entry, latLng) {
    const latitude = entry.querySelector('[name="location_latitude[]"]');
    const longitude = entry.querySelector('[name="location_longitude[]"]');
    if (!latitude || !longitude) return;
    latitude.value = latLng.lat.toFixed(6);
    longitude.value = latLng.lng.toFixed(6);
  }

  function coordinateForEntry(entry) {
    const latitude = entry.querySelector('[name="location_latitude[]"]');
    const longitude = entry.querySelector('[name="location_longitude[]"]');
    if (!latitude || !longitude) return null;
    const lat = readCoordinate(latitude);
    const lng = readCoordinate(longitude);
    if (lat === null || lng === null || (lat === 0 && lng === 0)) return null;
    return L.latLng(lat, lng);
  }

  function wait(milliseconds) {
    return new Promise((resolve) => {
      globalThis.setTimeout(resolve, milliseconds);
    });
  }

  function geocodeUrlFor(name) {
    const url = new URL(NOMINATIM_SEARCH_URL);
    url.searchParams.set('format', 'json');
    url.searchParams.set('q', name);
    url.searchParams.set('limit', '1');
    return url;
  }

  function firstCoordinate(results) {
    if (!Array.isArray(results)) return null;

    const match = results.find((result) => {
      const lat = Number.parseFloat(result.lat);
      const lng = Number.parseFloat(result.lon);
      return Number.isFinite(lat) && Number.isFinite(lng);
    });
    if (!match) return null;

    return {
      lat: Number.parseFloat(match.lat),
      lng: Number.parseFloat(match.lon),
      displayName: match.display_name || '',
    };
  }

  async function geocodeName(name) {
    const cacheKey = name.trim().toLocaleLowerCase();
    if (geocodeCache.has(cacheKey)) return geocodeCache.get(cacheKey);

    const request = geocodeQueue.then(async () => {
      const delay = Math.max(0, nextGeocodeAt - Date.now());
      if (delay) await wait(delay);
      nextGeocodeAt = Date.now() + NOMINATIM_MIN_INTERVAL_MS;

      const response = await fetch(geocodeUrlFor(name), {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Nominatim returned ${response.status}`);
      }

      const coordinate = firstCoordinate(await response.json());
      geocodeCache.set(cacheKey, coordinate);
      return coordinate;
    });

    geocodeQueue = request.catch(() => {});
    return request;
  }

  function expenseMarkup() {
    return `
      <div class="expense-entry">
        <div class="flex-1 min-w-32">
          <label class="form-label">支出類型</label>
          <select data-expense-type class="form-select form-select-sm">
            <option value="meal">餐飲</option>
            <option value="lodging">住宿</option>
            <option value="transport">交通</option>
            <option value="ticket">門票</option>
            <option value="shopping">購物</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div class="flex-1 min-w-32">
          <label class="form-label">金額</label>
          <input data-expense-amount type="number" step="0.01" class="form-control form-control-sm" placeholder="金額">
        </div>
        <button type="button" class="btn btn-outline-danger btn-sm remove-expense-btn" onclick="this.closest('.expense-entry').remove()">
          <i class="ri-delete-bin-line"></i>
          移除
        </button>
      </div>
    `;
  }

  function expenseHeaderMarkup() {
    return `
      <div class="expense-header">
        <h6 class="expenses-title">
          <i class="ri-wallet-3-line"></i>
          支出記錄
        </h6>
        <button type="button" class="btn btn-outline-primary btn-sm" onclick="addExpense(this)">
          <i class="ri-add-line"></i>
          新增支出
        </button>
      </div>
    `;
  }

  globalThis.addExpense = function addExpense(button) {
    const expenseList = button.closest('.expense-list');
    expenseList.insertAdjacentHTML('beforeend', expenseMarkup());
    setExpenseNames();
  };

  globalThis.addLocation = function addLocation() {
    const container = document.getElementById('locations-container');
    const source = container.querySelector('[data-location-entry]');
    if (!source) return;

    const clone = source.cloneNode(true);
    delete clone.dataset.routeEditorBound;
    clone.querySelectorAll('input, textarea').forEach((field) => {
      field.value = '';
    });
    clone.querySelectorAll('select').forEach((field) => {
      field.selectedIndex = 0;
    });
    const expenseList = clone.querySelector('.expense-list');
    if (expenseList) expenseList.innerHTML = expenseHeaderMarkup();
    container.appendChild(clone);
    document.dispatchEvent(new CustomEvent('route:entriesChanged'));
  };

  globalThis.removeLocation = function removeLocation(button) {
    const container = document.getElementById('locations-container');
    const entry = button.closest('[data-location-entry]');
    if (!entry || container.children.length <= 1) {
      alert('至少要有一個地點。');
      return;
    }
    entry.remove();
    document.dispatchEvent(new CustomEvent('route:entriesChanged'));
  };

  globalThis.moveLocation = function moveLocation(button, direction) {
    const container = document.getElementById('locations-container');
    const entry = button.closest('[data-location-entry]');
    if (!container || !entry) return;

    const target = direction === 'up' ? entry.previousElementSibling : entry.nextElementSibling;
    if (!target) return;

    if (direction === 'up') {
      container.insertBefore(entry, target);
    } else {
      container.insertBefore(target, entry);
    }

    console.info('Itinerary location order changed.', {
      direction,
      location: entryName(entry),
    });
    document.dispatchEvent(new CustomEvent('route:entriesChanged', { detail: { entry } }));
  };

  function setMarkerLabel(marker, entry) {
    const label = entryName(entry);
    if (marker.getTooltip()) {
      marker.setTooltipContent(markerLabelElement(label));
    } else {
      marker.bindTooltip(markerLabelElement(label), {
        direction: 'top',
        offset: [0, -10],
        opacity: 0.9,
        permanent: true,
      });
    }

    if (marker.getPopup()) {
      marker.setPopupContent(markerLabelElement(label));
    } else {
      marker.bindPopup(markerLabelElement(label));
    }
  }

  function initRouteEditor(editor) {
    if (!globalThis.L) return;

    const mapElement = editor.querySelector('[data-route-map]');
    const message = editor.querySelector('[data-route-message]');
    const serviceUrl = editor.dataset.routingServiceUrl || '';
    const routingProfile = editor.dataset.routingProfile || 'driving';
    const map = L.map(mapElement);
    const markers = new Map();
    let routeControl = null;
    let activeEntry = null;

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    function showMessage(text) {
      if (!message) return;
      message.textContent = text;
      message.hidden = !text;
    }

    function setActiveEntry(entry) {
      activeEntry = entry;
      getEntries().forEach((item) => item.classList.toggle('ring-2', item === activeEntry));
      getEntries().forEach((item) => item.classList.toggle('ring-coast-200', item === activeEntry));
    }

    function upsertMarker(entry, latLng) {
      let marker = markers.get(entry);
      if (!marker) {
        marker = L.marker(latLng, { draggable: true }).addTo(map);
        marker.on('dragend', () => {
          setEntryCoordinate(entry, marker.getLatLng());
          console.info('Route marker moved after drag.', { location: entryName(entry) });
          updateRoute();
        });
        markers.set(entry, marker);
      }
      marker.setLatLng(latLng);
      setMarkerLabel(marker, entry);
    }

    async function geocodeEntry(entry) {
      const nameInput = entry.querySelector('[name="location_name[]"]');
      const name = nameInput ? nameInput.value.trim() : '';
      if (!name) return;
      if (entry.dataset.lastGeocodedName === name && coordinateForEntry(entry)) return;

      try {
        // Nominatim disallows autocomplete, so geocode only after the user commits the field value.
        console.info('Geocoding location name with Nominatim.', { location: name });
        const coordinate = await geocodeName(name);
        if (!coordinate) {
          console.warn('Nominatim returned no coordinate for location name.', { location: name });
          showMessage(`找不到「${name}」的地理座標，請調整地點名稱或直接點選地圖。`);
          return;
        }

        const latLng = L.latLng(coordinate.lat, coordinate.lng);
        setEntryCoordinate(entry, latLng);
        upsertMarker(entry, latLng);
        setActiveEntry(entry);
        entry.dataset.lastGeocodedName = name;
        updateRoute();
      } catch (error) {
        console.error('Nominatim geocoding failed.', error);
        showMessage(`無法查詢「${name}」的地理座標，請稍後重試或直接點選地圖。`);
      }
    }

    function bindEntryEvents(entry) {
      if (entry.dataset.routeEditorBound === 'true') return;
      entry.dataset.routeEditorBound = 'true';

      entry.addEventListener('focusin', () => setActiveEntry(entry));
      entry.querySelectorAll('[name="location_latitude[]"], [name="location_longitude[]"]').forEach((field) => {
        field.addEventListener('change', updateRoute);
      });

      const nameInput = entry.querySelector('[name="location_name[]"]');
      if (!nameInput) return;
      nameInput.addEventListener('input', () => {
        const marker = markers.get(entry);
        if (marker) setMarkerLabel(marker, entry);
      });
      nameInput.addEventListener('change', () => geocodeEntry(entry));
      nameInput.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        geocodeEntry(entry);
        nameInput.blur();
      });
    }

    function bindEntries() {
      getEntries().forEach(bindEntryEvents);
    }

    function syncMarkers() {
      const entries = getEntries();
      for (const [entry, marker] of markers.entries()) {
        if (!entries.includes(entry)) {
          marker.remove();
          markers.delete(entry);
        }
      }
      entries.forEach((entry) => {
        const coordinate = coordinateForEntry(entry);
        if (coordinate) upsertMarker(entry, coordinate);
      });
    }

    function routeWaypoints() {
      return getEntries().map(coordinateForEntry).filter(Boolean);
    }

    function updateRoute() {
      setExpenseNames();
      setRouteOrders();
      updateLocationOrderControls();
      syncMarkers();

      const waypoints = routeWaypoints();
      if (waypoints.length < 2) {
        if (routeControl) {
          routeControl.remove();
          routeControl = null;
        }
        showMessage('至少需要兩個已定位的地點才能規劃路線。');
      } else if (!serviceUrl) {
        showMessage('尚未設定 ROUTING_SERVICE_URL，因此目前只顯示地點標記。');
      } else if (globalThis.L.Routing) {
        showMessage('');
        if (!routeControl) {
          routeControl = L.Routing.control({
            router: L.Routing.osrmv1({ serviceUrl, profile: routingProfile }),
            routeWhileDragging: false,
            addWaypoints: false,
            draggableWaypoints: false,
            showAlternatives: false,
            createMarker: () => null,
          }).addTo(map);
          routeControl.on('routingerror', (event) => {
            console.error('Leaflet Routing Machine route request failed.', event.error || event);
            const osrmFormatMessage = '路線規劃失敗，請確認 ROUTING_SERVICE_URL 使用 OSRM v1 格式，例如 https://router.project-osrm.org/route/v1。';
            const temporaryFailureMessage = '路線服務暫時不可用，請稍後重試。';
            showMessage(serviceUrl.includes('/route/v1') ? temporaryFailureMessage : osrmFormatMessage);
          });
        }
        routeControl.setWaypoints(waypoints);
      }

      if (waypoints.length) {
        map.fitBounds(L.latLngBounds(waypoints).pad(0.2), { maxZoom: 14 });
      } else {
        map.setView(DEFAULT_CENTER, 12);
      }
    }

    bindEntries();

    document.addEventListener('route:entriesChanged', (event) => {
      bindEntries();
      if (event.detail?.entry) setActiveEntry(event.detail.entry);
      updateRoute();
    });

    map.on('click', (event) => {
      const entry = activeEntry || getEntries().find((item) => !coordinateForEntry(item)) || getEntries().at(-1);
      if (!entry) return;
      setEntryCoordinate(entry, event.latlng);
      upsertMarker(entry, event.latlng);
      setActiveEntry(entry);
      updateRoute();
    });

    if (globalThis.L.Control?.Geocoder) {
      L.Control.geocoder({
        defaultMarkGeocode: false,
        placeholder: '搜尋地點或地址',
      })
        .on('markgeocode', (event) => {
          const entry = activeEntry || getEntries().find((item) => !coordinateForEntry(item)) || getEntries().at(-1);
          if (!entry) return;
          const center = event.geocode.center;
          const nameInput = entry.querySelector('[name="location_name[]"]');
          if (nameInput && !nameInput.value) nameInput.value = event.geocode.name;
          setEntryCoordinate(entry, center);
          upsertMarker(entry, center);
          setActiveEntry(entry);
          updateRoute();
        })
        .addTo(map);
    }

    const form = editor.closest('form');
    if (form) {
      form.addEventListener('submit', () => {
        setExpenseNames();
        setRouteOrders();
      });
    }

    setActiveEntry(getEntries()[0] || null);
    updateRoute();
    setTimeout(() => map.invalidateSize(), 50);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-route-editor]').forEach(initRouteEditor);
  });
})();
