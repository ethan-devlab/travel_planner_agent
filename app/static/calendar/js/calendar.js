!function() {
  const API = {
    events: '/api/events/',
    addEvent: '/api/add_event/',
    deleteEvent: (eventId) => '/api/delete_event/' + eventId + '/',
  };

  const SELECTORS = {
    calendar: '#calendar',
    addButton: '#add-event-button',
    eventForm: '.event-form',
    eventName: '#event-name',
    eventDate: '#event-date',
    eventColor: '#event-color',
  };

  const MESSAGES = {
    addRequiredFields: '請填寫所有欄位',
    addFailed: '新增活動失敗，請重試',
    deleteConfirm: '確定要刪除此活動嗎？',
    deleteFailed: '刪除失敗，請重試',
    emptyDay: '此日無活動',
  };

  const COLOR_TYPE_MAP = {
    orange: '工作',
    blue: '運動',
    yellow: '家庭',
    green: '旅行',
  };

  const today = moment();

  function eventTypeFor(color) {
    return COLOR_TYPE_MAP[color] || '其他';
  }

  function normalizeEvent(event) {
    const date = moment.isMoment(event.date) ? event.date : moment(event.date);
    return {
      id: event.id,
      eventName: event.eventName,
      calendar: event.calendar || event.color,
      color: event.color,
      type: event.type || eventTypeFor(event.color),
      date,
    };
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, { mode: 'same-origin', ...options });
    let payload = null;

    try {
      payload = await response.json();
    } catch (error) {
      if (response.ok) throw error;
    }

    if (!response.ok) {
      throw new Error(payload?.error || 'Request failed with status ' + response.status);
    }

    return payload;
  }

  function fetchEvents() {
    return fetchJson(API.events);
  }

  function createCalendarEvent(payload) {
    return fetchJson(API.addEvent, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken(),
      },
      body: JSON.stringify(payload),
    });
  }

  function removeCalendarEvent(eventId) {
    return fetchJson(API.deleteEvent(eventId), {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': getCSRFToken(),
      },
    });
  }

  function Calendar(selector, events) {
    this.el = document.querySelector(selector);
    this.events = events.map(normalizeEvent);
    this.current = moment().date(1);
    this.next = true;

    if (!this.el) {
      console.warn('Calendar root element was not found.', { selector });
      return;
    }

    this.draw();
    const current = this.el.querySelector('.today');
    if (current) {
      globalThis.setTimeout(() => this.openDay(current), 500);
    }
  }

  Calendar.prototype.setEvents = function(events) {
    this.events = events.map(normalizeEvent);
  };

  Calendar.prototype.draw = function() {
    if (!this.el) return;
    this.drawHeader();
    this.drawMonth();
  };

  Calendar.prototype.drawHeader = function() {
    if (!this.header) {
      this.header = createElement('div', 'header');
      this.header.className = 'header';

      this.title = createElement('h1');

      const right = createElement('div', 'right');
      right.addEventListener('click', () => this.nextMonth());

      const left = createElement('div', 'left');
      left.addEventListener('click', () => this.prevMonth());

      this.header.appendChild(this.title);
      this.header.appendChild(right);
      this.header.appendChild(left);
      this.el.appendChild(this.header);
    }

    this.title.textContent = this.current.format('MMMM YYYY');
  };

  Calendar.prototype.drawMonth = function() {
    this.setEvents(this.events);

    if (this.month) {
      const oldMonth = this.month;
      let rendered = false;
      const renderNextMonth = () => {
        if (rendered) return;
        rendered = true;
        oldMonth.remove();
        this.renderMonth('month');
        globalThis.setTimeout(() => {
          this.month.className = 'month in ' + (this.next ? 'next' : 'prev');
        }, 16);
      };

      oldMonth.className = 'month out ' + (this.next ? 'next' : 'prev');
      oldMonth.addEventListener('webkitAnimationEnd', renderNextMonth, { once: true });
      oldMonth.addEventListener('animationend', renderNextMonth, { once: true });
      globalThis.setTimeout(renderNextMonth, 350);
    } else {
      this.renderMonth('month new');
    }
  };

  Calendar.prototype.renderMonth = function(className) {
    this.month = createElement('div', className);
    this.week = null;
    this.el.appendChild(this.month);
    this.backFill();
    this.currentMonth();
    this.forwardFill();
  };

  Calendar.prototype.backFill = function() {
    const clone = this.current.clone();
    const dayOfWeek = clone.day();

    if (!dayOfWeek) return;

    clone.subtract('days', dayOfWeek + 1);
    for (let i = dayOfWeek; i > 0; i--) {
      this.drawDay(clone.add('days', 1));
    }
  };

  Calendar.prototype.forwardFill = function() {
    const clone = this.current.clone().add('months', 1).subtract('days', 1);
    const dayOfWeek = clone.day();

    if (dayOfWeek === 6) return;

    for (let i = dayOfWeek; i < 6; i++) {
      this.drawDay(clone.add('days', 1));
    }
  };

  Calendar.prototype.currentMonth = function() {
    const clone = this.current.clone();

    while (clone.month() === this.current.month()) {
      this.drawDay(clone);
      clone.add('days', 1);
    }
  };

  Calendar.prototype.getWeek = function(day) {
    if (!this.week || day.day() === 0) {
      this.week = createElement('div', 'week');
      this.month.appendChild(this.week);
    }
  };

  Calendar.prototype.drawDay = function(day) {
    const renderedDay = day.clone();
    this.getWeek(renderedDay);

    const outer = createElement('div', this.getDayClass(renderedDay));
    outer.dataset.date = renderedDay.format('YYYY-MM-DD');
    outer.addEventListener('click', () => this.openDay(outer));

    const name = createElement('div', 'day-name', renderedDay.format('ddd'));
    const number = createElement('div', 'day-number', renderedDay.format('DD'));
    const events = createElement('div', 'day-events');

    this.drawEvents(renderedDay, events);

    outer.appendChild(name);
    outer.appendChild(number);
    outer.appendChild(events);
    this.week.appendChild(outer);
  };

  Calendar.prototype.eventsForDay = function(day) {
    return this.events.filter((event) => event.date.isSame(day, 'day'));
  };

  Calendar.prototype.drawEvents = function(day, element) {
    if (day.month() !== this.current.month()) return;

    this.eventsForDay(day).forEach((event) => {
      const eventIndicator = createElement('span', 'event-indicator ' + event.color, event.type || '活動');
      eventIndicator.title = event.eventName;
      element.appendChild(eventIndicator);
    });
  };

  Calendar.prototype.getDayClass = function(day) {
    const classes = ['day'];
    if (day.month() !== this.current.month()) {
      classes.push('other');
    } else if (today.isSame(day, 'day')) {
      classes.push('today');
    }
    return classes.join(' ');
  };

  Calendar.prototype.openDay = function(el) {
    const day = moment(el.dataset.date, 'YYYY-MM-DD');
    if (!day.isValid()) return;

    document.querySelectorAll('.details').forEach((opened) => {
      if (opened.parentNode !== el.parentNode) {
        opened.remove();
      }
    });

    const details = this.detailsForElement(el);
    const events = this.eventsForDay(day);
    const oldEvents = details.querySelector('.events');
    if (oldEvents) oldEvents.remove();

    this.renderEvents(events, details);

    const arrow = details.querySelector('.arrow');
    arrow.style.left = el.offsetLeft - el.parentNode.offsetLeft + 27 + 'px';
  };

  Calendar.prototype.openDayForDate = function(day) {
    const targetDay = normalizeMoment(day);
    if (!targetDay || !targetDay.isSame(this.current, 'month')) return;

    const dayElement = this.dayElementFor(targetDay);
    if (dayElement) this.openDay(dayElement);
  };

  Calendar.prototype.detailsForElement = function(el) {
    let details = el.parentNode.querySelector('.details');
    if (details) {
      if (!details.querySelector('.arrow')) {
        details.insertBefore(createElement('div', 'arrow'), details.firstChild);
      }
      return details;
    }

    details = createElement('div', 'details in');
    details.appendChild(createElement('div', 'arrow'));
    el.parentNode.appendChild(details);
    return details;
  };

  Calendar.prototype.renderEvents = function(events, element) {
    const currentWrapper = element.querySelector('.events');
    const wrapper = createElement('div', 'events in' + (currentWrapper ? ' new' : ''));

    events.forEach((event) => {
      wrapper.appendChild(this.eventElement(event));
    });

    if (!events.length) {
      wrapper.appendChild(emptyEventElement());
    }

    if (currentWrapper) currentWrapper.replaceWith(wrapper);
    else element.appendChild(wrapper);
  };

  Calendar.prototype.eventElement = function(event) {
    const eventDiv = createElement('div', 'event');
    const eventContent = createElement('div', 'event-content');
    const square = createElement('div', 'event-category ' + event.color);
    const name = createElement('span', 'event-name', event.eventName);
    const type = createElement('span', 'event-type ' + event.color, event.type || '其他');

    eventContent.appendChild(square);
    eventContent.appendChild(name);
    eventContent.appendChild(type);

    const deleteBtn = createElement('button', 'delete-btn');
    deleteBtn.type = 'button';
    deleteBtn.setAttribute('aria-label', '刪除活動');
    deleteBtn.innerHTML = '<i class="ri-delete-bin-line"></i>';
    deleteBtn.addEventListener('click', (eventObject) => {
      eventObject.stopPropagation();
      this.deleteEvent(event.id, eventDiv);
    });

    eventDiv.appendChild(eventContent);
    eventDiv.appendChild(deleteBtn);
    return eventDiv;
  };

  Calendar.prototype.refreshDayIndicators = function(day) {
    const targetDay = normalizeMoment(day);
    if (!targetDay || !targetDay.isSame(this.current, 'month')) return;

    const dayElement = this.dayElementFor(targetDay);
    if (!dayElement) return;

    const dayEvents = dayElement.querySelector('.day-events');
    if (!dayEvents) return;

    dayEvents.replaceChildren();
    this.drawEvents(targetDay, dayEvents);
  };

  Calendar.prototype.dayElementFor = function(day) {
    const targetDate = day.format('YYYY-MM-DD');
    return this.el.querySelector('.month .day[data-date="' + targetDate + '"]');
  };

  Calendar.prototype.deleteEvent = async function(eventId, eventElement) {
    if (!confirm(MESSAGES.deleteConfirm)) return;

    const deletedEvent = this.events.find((event) => event.id === eventId);

    try {
      const data = await removeCalendarEvent(eventId);
      if (data.status !== 'ok') {
        throw new Error(data.error || 'Delete response was not ok.');
      }

      globalThis.data = globalThis.data.filter((event) => event.id !== eventId);
      this.setEvents(globalThis.data);
      this.removeEventElement(eventElement, deletedEvent?.date);
    } catch (error) {
      console.error('Delete event failed.', error);
      alert(MESSAGES.deleteFailed);
    }
  };

  Calendar.prototype.removeEventElement = function(eventElement, eventDate) {
    const eventsContainer = eventElement.closest('.events');
    eventElement.style.opacity = '0';
    eventElement.style.transform = 'translateX(-100%)';

    globalThis.setTimeout(() => {
      eventElement.remove();

      if (eventsContainer && !eventsContainer.querySelector('.event:not(.empty)')) {
        eventsContainer.querySelectorAll('.event.empty').forEach((emptyEvent) => emptyEvent.remove());
        eventsContainer.appendChild(emptyEventElement());
      }

      this.refreshDayIndicators(eventDate);
    }, 300);
  };

  Calendar.prototype.nextMonth = function() {
    this.current.add('months', 1);
    this.next = true;
    this.draw();
  };

  Calendar.prototype.prevMonth = function() {
    this.current.subtract('months', 1);
    this.next = false;
    this.draw();
  };

  function normalizeMoment(day) {
    if (!day) return null;
    const parsed = moment.isMoment(day) ? day.clone() : moment(day);
    return parsed.isValid() ? parsed : null;
  }

  function emptyEventElement() {
    const div = createElement('div', 'event empty');
    div.appendChild(createElement('span', '', MESSAGES.emptyDay));
    return div;
  }

  function readEventForm() {
    return {
      name: document.querySelector(SELECTORS.eventName)?.value.trim() || '',
      date: document.querySelector(SELECTORS.eventDate)?.value || '',
      color: document.querySelector(SELECTORS.eventColor)?.value || '',
    };
  }

  function resetEventForm() {
    const name = document.querySelector(SELECTORS.eventName);
    const date = document.querySelector(SELECTORS.eventDate);
    const color = document.querySelector(SELECTORS.eventColor);

    if (name) name.value = '';
    if (date) date.value = '';
    if (color) color.value = 'orange';
  }

  async function addEvent() {
    const form = readEventForm();

    if (!form.name || !form.date || !form.color) {
      alert(MESSAGES.addRequiredFields);
      return;
    }

    try {
      const data = await createCalendarEvent({
        eventName: form.name,
        date: form.date,
        color: form.color,
      });

      if (data.status !== 'ok') {
        throw new Error(data.error || 'Add response was not ok.');
      }

      const event = normalizeEvent({
        id: data.id,
        eventName: form.name,
        calendar: form.color,
        color: form.color,
        date: form.date,
      });

      globalThis.data.push(event);
      globalThis.calendar.setEvents(globalThis.data);
      globalThis.calendar.refreshDayIndicators(event.date);
      resetEventForm();
      globalThis.calendar.openDayForDate(event.date);
    } catch (error) {
      console.error('Add event failed.', error);
      alert(MESSAGES.addFailed);
    }
  }

  function bindEventForm() {
    const button = document.querySelector(SELECTORS.addButton);
    if (button) {
      button.addEventListener('click', addEvent);
    }

    const form = document.querySelector(SELECTORS.eventForm);
    if (form) {
      form.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          addEvent();
        }
      });
    }
  }

  async function initCalendar() {
    try {
      const events = await fetchEvents();
      globalThis.data = events.map(normalizeEvent);
      globalThis.calendar = new Calendar(SELECTORS.calendar, globalThis.data);
      console.info('Calendar initialized.', { eventCount: globalThis.data.length });
    } catch (error) {
      console.error('Calendar initialization failed.', error);
    }
  }

  function createElement(tagName, className, innerText) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (innerText !== undefined) {
      element.innerText = element.textContent = innerText;
    }
    return element;
  }

  globalThis.Calendar = Calendar;
  globalThis.addEvent = addEvent;

  document.addEventListener('DOMContentLoaded', () => {
    bindEventForm();
    initCalendar();
  });
}();

function getCSRFToken() {
  // Prefer Django's masked DOM token; fall back to the default CSRF cookie.
  const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
  if (tokenInput?.value) {
    return tokenInput.value;
  }

  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (const rawCookie of cookies) {
    const cookie = rawCookie.trim();
    if (cookie.startsWith(name + '=')) {
      return decodeURIComponent(cookie.substring(name.length + 1));
    }
  }
  return '';
}
