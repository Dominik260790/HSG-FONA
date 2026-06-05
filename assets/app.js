document.addEventListener('DOMContentLoaded', async function () {
  const calendarEl = document.getElementById('calendar');
  const controlsEl = document.querySelector('.controls');

  const response = await fetch('data/events.json?ts=' + Date.now());
  const rawEvents = await response.json();

  const urlParams = new URLSearchParams(window.location.search);
  const hallParam = urlParams.get('halle');

  const preselectedHalls = hallParam
    ? hallParam.split(',').map(value => value.trim())
    : null;

  console.log('Geladene Termine:', rawEvents.length);
  console.log('Gefundene Hallen:', [...new Set(rawEvents.map(e => e.hall_id + ' - ' + e.hall))]);
  console.log('Gefundene Typen:', [...new Set(rawEvents.map(e => e.type))]);
  console.log('Vorausgewählte Hallen:', preselectedHalls);

  function uniqueBy(array, keyFn) {
    const map = new Map();

    array.forEach(item => {
      const key = keyFn(item);

      if (!map.has(key)) {
        map.set(key, item);
      }
    });

    return Array.from(map.values());
  }

  function typeLabel(type) {
   const labels = {
  game: 'Spiele',
  training: 'Training',
  blocked: 'Belegt',
  football: 'Fußballerzeit',
  optional: 'Optional',
  weekend: 'Wochenendbelegung',
  event: 'Zusatztermine',
  camp: 'Trainingslager',
  tournament: 'Turnier'
};
    return labels[type] || type;
  }

  function slugForHall(hallId, hallName) {
    const known = {
      '140702': 'alt-duvenstedt',
      '140704': 'bsh',
      '140703': 'realschule',
      '140717': 'nuebbel',
      'KRUMMENORT': 'krummenort'
    };

    if (known[hallId]) {
      return known[hallId];
    }

    return hallName
      .toLowerCase()
      .replaceAll('ä', 'ae')
      .replaceAll('ö', 'oe')
      .replaceAll('ü', 'ue')
      .replaceAll('ß', 'ss')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  const halls = uniqueBy(
    rawEvents
      .filter(e => e.hall_id && e.hall)
      .map(e => ({
        id: e.hall_id,
        name: e.hall
      })),
    h => h.id
  ).sort((a, b) => a.name.localeCompare(b.name, 'de'));

  const types = uniqueBy(
    rawEvents
      .filter(e => e.type)
      .map(e => ({
        id: e.type,
        name: typeLabel(e.type)
      })),
    t => t.id
  ).sort((a, b) => a.name.localeCompare(b.name, 'de'));

  function buildControls() {
    controlsEl.innerHTML = '';

    const hallTitle = document.createElement('strong');
    hallTitle.textContent = 'Hallen:';
    controlsEl.appendChild(hallTitle);
    controlsEl.appendChild(document.createTextNode(' '));

    halls.forEach(hall => {
      const label = document.createElement('label');
      label.style.marginRight = '12px';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'hall-filter';
      input.value = hall.id;

      input.checked = preselectedHalls
        ? preselectedHalls.includes(hall.id)
        : true;

      label.appendChild(input);
      label.appendChild(document.createTextNode(' ' + hall.name));

      controlsEl.appendChild(label);
    });

    controlsEl.appendChild(document.createElement('br'));
    controlsEl.appendChild(document.createElement('br'));

    const typeTitle = document.createElement('strong');
    typeTitle.textContent = 'Terminarten:';
    controlsEl.appendChild(typeTitle);
    controlsEl.appendChild(document.createTextNode(' '));

    types.forEach(type => {
      const label = document.createElement('label');
      label.style.marginRight = '12px';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'type-filter';
      input.value = type.id;
      input.checked = true;

      label.appendChild(input);
      label.appendChild(document.createTextNode(' ' + type.name));

      controlsEl.appendChild(label);
    });

    controlsEl.appendChild(document.createElement('br'));
    controlsEl.appendChild(document.createElement('br'));

    const icalTitle = document.createElement('strong');
    icalTitle.textContent = 'iCal:';
    controlsEl.appendChild(icalTitle);
    controlsEl.appendChild(document.createTextNode(' '));

    const totalLink = document.createElement('a');
    totalLink.href = 'calendars/gesamt.ics';
    totalLink.textContent = 'Gesamt-iCal';
    totalLink.style.marginRight = '12px';
    controlsEl.appendChild(totalLink);

    halls.forEach(hall => {
      const link = document.createElement('a');
      link.href = 'calendars/' + slugForHall(hall.id, hall.name) + '.ics';
      link.textContent = hall.name + '-iCal';
      link.style.marginRight = '12px';
      controlsEl.appendChild(link);
    });

    controlsEl.appendChild(document.createElement('br'));
    controlsEl.appendChild(document.createElement('br'));

    const viewTitle = document.createElement('strong');
    viewTitle.textContent = 'Einzelansichten:';
    controlsEl.appendChild(viewTitle);
    controlsEl.appendChild(document.createTextNode(' '));

    const allViewLink = document.createElement('a');
    allViewLink.href = window.location.pathname;
    allViewLink.textContent = 'Alle Hallen';
    allViewLink.style.marginRight = '12px';
    controlsEl.appendChild(allViewLink);

    halls.forEach(hall => {
      const link = document.createElement('a');
      link.href = window.location.pathname + '?halle=' + encodeURIComponent(hall.id);
      link.textContent = hall.name;
      link.style.marginRight = '12px';
      controlsEl.appendChild(link);
    });
  }

  function selectedValues(selector) {
    return Array.from(document.querySelectorAll(selector + ':checked'))
      .map(el => el.value);
  }

  function filteredEvents() {
    const selectedHalls = selectedValues('.hall-filter');
    const selectedTypes = selectedValues('.type-filter');

    return rawEvents
      .filter(e => selectedHalls.includes(e.hall_id))
      .filter(e => selectedTypes.includes(e.type))
      .map(e => ({
        id: e.id,
        title: e.title + ' · ' + e.hall,
        start: e.start,
        end: e.end,
        color: e.color || undefined,
        url: e.url || undefined,
        extendedProps: e
      }));
  }

  buildControls();

  const calendar = new FullCalendar.Calendar(calendarEl, {
    locale: 'de',
    initialView: 'timeGridWeek',
    initialDate: new Date(),
    firstDay: 1,
    height: 'auto',
    nowIndicator: true,
    slotMinTime: '08:00:00',
    slotMaxTime: '23:00:00',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek'
    },
    events: filteredEvents(),
    eventClick: function(info) {
      const e = info.event.extendedProps;

      alert([
        info.event.title,
        'Halle: ' + e.hall,
        'Typ: ' + e.type,
        e.description ? 'Info: ' + e.description : '',
        e.url ? 'Quelle: ' + e.url : ''
      ].filter(Boolean).join('\n'));
    }
  });

  calendar.render();

  document.querySelectorAll('.hall-filter,.type-filter').forEach(el => {
    el.addEventListener('change', () => {
      calendar.removeAllEvents();
      calendar.addEventSource(filteredEvents());
    });
  });
});
