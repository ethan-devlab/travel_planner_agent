(function () {
  const DEFAULT_CENTER = [25.0375, 121.5637];

  function markerLabelElement(text) {
    const element = document.createElement('span');
    element.textContent = text || '地點';
    return element;
  }

  function initRoutePreview(preview) {
    if (!globalThis.L) return;

    const dataElement = document.getElementById(preview.dataset.routeDataId);
    const message = preview.querySelector('[data-route-message]');
    const mapElement = preview.querySelector('[data-route-map]');
    const serviceUrl = preview.dataset.routingServiceUrl || '';
    const routingProfile = preview.dataset.routingProfile || 'driving';
    const waypoints = dataElement ? JSON.parse(dataElement.textContent) : [];
    const coordinates = waypoints
      .map((point) => L.latLng(point.lat, point.lng))
      .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));

    const map = L.map(mapElement);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    waypoints.forEach((point) => {
      if (Number.isFinite(point.lat) && Number.isFinite(point.lng)) {
        L.marker([point.lat, point.lng])
          .addTo(map)
          .bindPopup(markerLabelElement(point.name))
          .bindTooltip(markerLabelElement(point.name), {
            direction: 'top',
            offset: [0, -10],
            opacity: 0.9,
            permanent: true,
          });
      }
    });

    if (coordinates.length >= 2 && serviceUrl && globalThis.L.Routing) {
      const routeControl = L.Routing.control({
        router: L.Routing.osrmv1({ serviceUrl, profile: routingProfile }),
        waypoints: coordinates,
        routeWhileDragging: false,
        addWaypoints: false,
        draggableWaypoints: false,
        showAlternatives: false,
        createMarker: () => null,
      });
      routeControl.on('routingerror', (event) => {
        console.error('Leaflet Routing Machine route preview request failed.', event.error || event);
        if (!message) return;
        const osrmFormatMessage = '路線預覽失敗，請確認 ROUTING_SERVICE_URL 使用 OSRM v1 格式，例如 https://router.project-osrm.org/route/v1。';
        const temporaryFailureMessage = '路線服務暫時不可用，請稍後重試。';
        message.textContent = serviceUrl.includes('/route/v1') ? temporaryFailureMessage : osrmFormatMessage;
        message.hidden = false;
      });
      routeControl.addTo(map);
      if (message) message.hidden = true;
    } else if (message) {
      message.textContent = coordinates.length < 2
        ? '至少需要兩個已定位的地點才能顯示路線。'
        : '尚未設定 ROUTING_SERVICE_URL，因此目前只顯示地點標記。';
      message.hidden = coordinates.length >= 2 && serviceUrl;
    }

    if (coordinates.length) {
      map.fitBounds(L.latLngBounds(coordinates).pad(0.2), { maxZoom: 14 });
    } else {
      map.setView(DEFAULT_CENTER, 12);
    }
    setTimeout(() => map.invalidateSize(), 50);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-route-preview]').forEach(initRoutePreview);
  });
})();
