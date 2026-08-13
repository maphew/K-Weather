(() => {
  const controls = document.querySelector("[data-date-range]");
  const startDate = document.querySelector('input[name="start"]');
  const endDate = document.querySelector('input[name="end"]');
  if (!controls || !startDate || !endDate) return;

  const startRange = controls.querySelector("[data-range-start]");
  const endRange = controls.querySelector("[data-range-end]");
  const dayMilliseconds = 24 * 60 * 60 * 1000;
  const minimum = Date.parse(`${startDate.min}T00:00:00Z`);
  const maximum = Date.parse(`${startDate.max}T00:00:00Z`);
  const days = Math.round((maximum - minimum) / dayMilliseconds);

  const offset = (value) =>
    Math.round((Date.parse(`${value}T00:00:00Z`) - minimum) / dayMilliseconds);
  const dateAt = (value) =>
    new Date(minimum + Number(value) * dayMilliseconds).toISOString().slice(0, 10);

  startRange.min = 0;
  startRange.max = days;
  endRange.min = 0;
  endRange.max = days;
  startRange.value = offset(startDate.value);
  endRange.value = offset(endDate.value);

  const updateRangeLimits = () => {
    startRange.max = endRange.value;
    endRange.min = startRange.value;
  };
  const updateSliders = () => {
    if (startDate.validity.valid) startRange.value = offset(startDate.value);
    if (endDate.validity.valid) endRange.value = offset(endDate.value);
    updateRangeLimits();
  };

  startRange.addEventListener("input", () => {
    startDate.value = dateAt(startRange.value);
    updateRangeLimits();
  });
  endRange.addEventListener("input", () => {
    endDate.value = dateAt(endRange.value);
    updateRangeLimits();
  });
  startDate.addEventListener("input", updateSliders);
  endDate.addEventListener("input", updateSliders);
  updateRangeLimits();
})();
