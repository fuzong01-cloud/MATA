<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useAttrs, watch } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  ariaLabel: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'change'])
const attrs = useAttrs()
const trigger = ref(null)
const popover = ref(null)
const isOpen = ref(false)
const activeIndex = ref(-1)
const popoverStyle = ref({ visibility: 'hidden' })
const openSide = ref('bottom')
const listboxId = `select-listbox-${Math.random().toString(36).slice(2)}`

const normalizedOptions = computed(() => props.options.map(option => {
  if (option && typeof option === 'object') {
    return { value: option.value ?? option.label ?? '', label: option.label ?? String(option.value ?? ''), disabled: Boolean(option.disabled) }
  }
  return { value: option, label: String(option ?? ''), disabled: false }
}))
const selectedIndex = computed(() => normalizedOptions.value.findIndex(option => option.value === props.modelValue))
const selectedOption = computed(() => normalizedOptions.value[selectedIndex.value])
const activeOptionId = computed(() => isOpen.value && activeIndex.value >= 0 ? `${listboxId}-option-${activeIndex.value}` : undefined)

function nearestEnabled(index, direction = 1) {
  const items = normalizedOptions.value
  if (!items.length) return -1
  let candidate = Math.min(Math.max(index, 0), items.length - 1)
  while (items[candidate]?.disabled) {
    candidate += direction
    if (candidate < 0 || candidate >= items.length) return -1
  }
  return candidate
}

function updatePosition() {
  const anchor = trigger.value?.getBoundingClientRect()
  const panel = popover.value
  if (!anchor || !panel) return

  const edge = 8
  const gap = 5
  const roomBelow = Math.max(0, window.innerHeight - anchor.bottom - gap - edge)
  const roomAbove = Math.max(0, anchor.top - gap - edge)
  const shouldOpenAbove = roomBelow < Math.min(180, panel.scrollHeight) && roomAbove > roomBelow
  const available = shouldOpenAbove ? roomAbove : roomBelow
  const maxHeight = Math.max(72, Math.min(320, available))
  const panelHeight = Math.min(panel.scrollHeight, maxHeight)
  const width = Math.min(anchor.width, window.innerWidth - edge * 2)
  const left = Math.min(Math.max(edge, anchor.left), window.innerWidth - width - edge)
  const top = shouldOpenAbove
    ? Math.max(edge, anchor.top - panelHeight - gap)
    : Math.min(anchor.bottom + gap, window.innerHeight - panelHeight - edge)

  openSide.value = shouldOpenAbove ? 'top' : 'bottom'
  popoverStyle.value = { position: 'fixed', top: `${top}px`, left: `${left}px`, width: `${width}px`, maxHeight: `${maxHeight}px`, visibility: 'visible' }
}

function onViewportChange() {
  if (isOpen.value) updatePosition()
}

function onDocumentPointerDown(event) {
  if (trigger.value?.contains(event.target) || popover.value?.contains(event.target)) return
  closeMenu()
}

function openMenu(preferredIndex = selectedIndex.value) {
  if (props.disabled || isOpen.value) return
  activeIndex.value = nearestEnabled(preferredIndex >= 0 ? preferredIndex : 0)
  isOpen.value = true
  popoverStyle.value = { visibility: 'hidden' }
  nextTick(() => {
    updatePosition()
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
    document.addEventListener('pointerdown', onDocumentPointerDown, true)
  })
}

function closeMenu() {
  if (!isOpen.value) return
  isOpen.value = false
  activeIndex.value = -1
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
}

function moveActive(direction) {
  const length = normalizedOptions.value.length
  if (!length) return
  let next = activeIndex.value
  for (let count = 0; count < length; count += 1) {
    next = (next + direction + length) % length
    if (!normalizedOptions.value[next]?.disabled) {
      activeIndex.value = next
      return
    }
  }
}

function choose(option, index) {
  if (option.disabled) return
  if (option.value !== props.modelValue) {
    emit('update:modelValue', option.value)
    emit('change', option.value)
  }
  activeIndex.value = index
  closeMenu()
}

function onKeydown(event) {
  if (event.key === 'Tab') {
    closeMenu()
    return
  }
  if (event.key === 'Escape') {
    if (isOpen.value) {
      event.preventDefault()
      closeMenu()
    }
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!isOpen.value) openMenu(event.key === 'ArrowDown' ? selectedIndex.value + 1 : selectedIndex.value - 1)
    else moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Home' || event.key === 'End') {
    if (!isOpen.value) return
    event.preventDefault()
    const destination = event.key === 'Home' ? 0 : normalizedOptions.value.length - 1
    activeIndex.value = nearestEnabled(destination, event.key === 'Home' ? 1 : -1)
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!isOpen.value) openMenu()
    else if (normalizedOptions.value[activeIndex.value]) choose(normalizedOptions.value[activeIndex.value], activeIndex.value)
  }
}

watch(() => props.options, async () => {
  if (!isOpen.value) return
  await nextTick()
  activeIndex.value = nearestEnabled(selectedIndex.value >= 0 ? selectedIndex.value : 0)
  updatePosition()
}, { deep: true })

watch([activeIndex, isOpen], async ([index, open]) => {
  if (!open || index < 0) return
  await nextTick()
  popover.value?.querySelectorAll('[role="option"]')[index]?.scrollIntoView({ block: 'nearest' })
})

onBeforeUnmount(closeMenu)
</script>

<template>
  <div class="custom-select" v-bind="attrs">
    <button
      ref="trigger"
      class="custom-select__trigger"
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      :aria-label="ariaLabel || undefined"
      :aria-expanded="isOpen"
      :aria-controls="isOpen ? listboxId : undefined"
      :aria-activedescendant="activeOptionId"
      :disabled="disabled"
      @click="isOpen ? closeMenu() : openMenu()"
      @keydown="onKeydown"
    >
      <span class="custom-select__value">{{ selectedOption?.label ?? placeholder }}</span>
      <ChevronDown class="custom-select__chevron" :size="16" :stroke-width="1.8" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <Transition name="select-menu">
        <div
          v-if="isOpen"
          ref="popover"
          class="custom-select__popover"
          :class="`is-${openSide}`"
          :style="popoverStyle"
          :id="listboxId"
          role="listbox"
          :aria-label="ariaLabel || '选项'"
          @keydown="onKeydown"
        >
          <button
            v-for="(option, index) in normalizedOptions"
            :id="`${listboxId}-option-${index}`"
            :key="String(option.value)"
            class="custom-select__option"
            :class="{ active: index === activeIndex, selected: index === selectedIndex }"
            type="button"
            role="option"
            :aria-selected="index === selectedIndex"
            :aria-disabled="option.disabled || undefined"
            :disabled="option.disabled"
            tabindex="-1"
            @mouseenter="activeIndex = index"
            @mousedown.prevent
            @click="choose(option, index)"
          >
            <span>{{ option.label }}</span>
            <Check v-if="index === selectedIndex" class="custom-select__check" :size="16" :stroke-width="2" aria-hidden="true" />
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-select { display: block; width: 100%; min-width: 0; }
.custom-select__trigger {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  width: 100%; min-width: 0; min-height: 42px; padding: 9px 12px;
  border: 1px solid #cbdeda; border-radius: 10px; background: #fff; color: #16343b;
  font: inherit; text-align: left; cursor: pointer;
  transition: border-color 140ms ease, background-color 140ms ease, box-shadow 140ms ease, color 140ms ease;
}
.custom-select__trigger:hover:not(:disabled) { border-color: #9fc9c1; background: #fcfefd; }
.custom-select .custom-select__trigger:focus-visible { outline: 2px solid #0d7774; outline-offset: 2px; border-color: #0d7774; }
.custom-select__trigger:disabled { color: #8a9b9a; background: #f2f6f5; cursor: not-allowed; }
.custom-select__value { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.custom-select__chevron { flex: none; color: #557672; transition: transform 150ms ease; }
.custom-select__trigger[aria-expanded="true"] .custom-select__chevron { transform: rotate(180deg); }
.custom-select__popover {
  z-index: 1200; overflow-y: auto; overscroll-behavior: contain;
  padding: 5px; border: 1px solid #d6e5e1; border-radius: 11px;
  background: #fff; box-shadow: 0 12px 32px #16343b1c, 0 2px 7px #16343b0b;
  scrollbar-width: thin; scrollbar-color: #c4d9d4 transparent;
}
.custom-select__option {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  width: 100%; min-height: 36px; padding: 8px 10px; border: 0; border-radius: 7px;
  background: transparent; color: #34545a; font: inherit; font-size: 13px; text-align: left; cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}
.custom-select__option:hover, .custom-select__option.active { background: #edf7f4; color: #0d7774; }
.custom-select__option.selected { background: #e5f3ef; color: #0d7774; font-weight: 650; }
.custom-select__option.selected.active, .custom-select__option.selected:hover { background: #dceee9; }
.custom-select__option:disabled { color: #9aacab; cursor: not-allowed; }
.custom-select__check { flex: none; color: #0d7774; }
:global(.select-menu-enter-active), :global(.select-menu-leave-active) { transition: opacity 150ms ease, transform 150ms ease; }
:global(.select-menu-enter-from), :global(.select-menu-leave-to) { opacity: 0; transform: translateY(4px); }
:global(.select-menu-enter-active.is-top), :global(.select-menu-leave-active.is-top) { transition: opacity 150ms ease, transform 150ms ease; }
:global(.select-menu-enter-from.is-top), :global(.select-menu-leave-to.is-top) { transform: translateY(-4px); }
@media (prefers-reduced-motion: reduce) {
  .custom-select__trigger, .custom-select__chevron, .custom-select__option { transition-duration: .01ms; }
  :global(.select-menu-enter-active), :global(.select-menu-leave-active) { transition-duration: .01ms; }
}
</style>
