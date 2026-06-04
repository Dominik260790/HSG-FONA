document.addEventListener('DOMContentLoaded', async function () {
  const calendarEl = document.getElementById('calendar');
  const response = await fetch('data/events.json?ts=' + Date.now());
  const rawEvents = await response.json();

  function selectedValues(selector) {
    return Array.from(document.querySelectorAll(selector + ':checked')).map(el => el.value);
  }

  function filteredEvents() {
    const halls = selectedValues('.hall-filter');
    const types = selectedValues('.type-filter');
    return rawEvents
      .filter(e => halls.includes(e.hall_id))
      .filter(e => types.includes(e.type))
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

  const calendar = new FullCalendar.Calendar(calendarEl, {
    locale: 'de',
    initialView: 'timeGridWeek',
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
        e.description ? 'Info: ' + e.description : ''
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
