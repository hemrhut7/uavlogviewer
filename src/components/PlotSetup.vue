<template>
  <div>
    <li class="type">
      <div v-b-toggle.plotsetupcontent>
        <a class="section">
          Plots Setup
          <i class="expand fas fa-caret-down"></i>
        </a>
      </div>
    </li>
    <b-collapse id="plotsetupcontent" class="menu-content collapse out" visible>
      <div v-for="(chart, chartIdx) in state.charts" :key="'chartArea' + chartIdx" class="chart-setup-area">
        <div class="chart-header">
           <span>Chart #{{ chartIdx + 1 }}</span>
           <a v-if="state.charts.length > 1" class="remove-button-chart" @click="removeChart(chartIdx)">
              <i class="fas fa-times-circle" title="Remove entire chart"></i>
           </a>
        </div>
        <ul class="colorpicker plot-wrapper-inner">
          <template v-if="chart.expressions.length">
            <template v-for="(field, index) in chart.expressions">
              <li class="field plotsetup" :key="'field' + chartIdx + '_' + index">
                <expression-editor v-model.lazy="field.name" v-debounce="1000" :suggestions="completionOptions" />
                <select v-model.number="field.axis">
                  <option v-for="axis in state.allAxis" :key="'axisnumber' + axis" :value="axis">{{ axis }}</option>
                </select>
                <select v-model="field.color" :style="{ color: field.color }">
                  <option v-for="color in state.allColors" :key="'axisColor' + color" :value="color"
                    :style="{ color: color }">■
                  </option>
                </select>
                <a class="remove-button" @click="removePlot(chartIdx, field.name)">
                  <i class="expand fas fa-trash" title="Remove data"></i>
                </a>
              </li>
              <li v-if="chart.expressionErrors[index]" :key="'field' + chartIdx + '_' + index + 'err'" class="error">
                <i class="fas fa-exclamation-circle error" :title="chart.expressionErrors[index]"></i>
                {{ chart.expressionErrors[index] }}
              </li>
            </template>
          </template>
          <li v-else>No expressions in this chart.</li>
        </ul>
        <div class="btns-wrapper">
          <button class="add-expression" @click="createNewExpression(chartIdx)">
            <i class="fa fa-plus" aria-hidden="true"></i>Add to Chart {{ chartIdx + 1 }}
          </button>
        </div>
      </div>
      <!-- GLOBAL BUTTONS -->
      <div class="btns-wrapper global-btns"
           style="flex-direction: column; align-items: center; gap: 10px;">
        <div class="global-settings" style="display: flex; gap: 15px; color: #fff;">
          <label style="cursor: pointer;">
            <input type="checkbox" v-model="state.syncZoom"> Sync Zoom
          </label>
          <label style="cursor: pointer;">
            <input type="checkbox" v-model="state.statsFullRange"
                   @change="$eventHub.$emit('recalc-stats')"> Full Range Stats
          </label>
        </div>
        <div style="display: flex; gap: 10px;">
          <button class="add-chart" @click="createNewChart">
             <i class="fa fa-plus-square" aria-hidden="true"></i>Add New Chart
          </button>
          <button v-if="state.charts.some(c => c.expressions.length > 0)"
                  class="save-preset" v-b-modal.modal-prevent-closing>
            <i class="fa fa-check-circle" aria-hidden="true"></i>Save Preset
          </button>
          <button class="save-preset" v-if="state.charts.some(c => c.expressions.length > 0)"
                  @click="clearAllPlots">
            <i class="fa fa-ban" aria-hidden="true"></i>
            clear all
          </button>
        </div>
      </div>
    </b-collapse>
    <!-- MODAL -->
    <b-modal id="modal-prevent-closing" ref="modal" @show="resetModal" @hidden="resetModal" @ok="handleOk">
      <form ref="form" @submit.stop.prevent="handleOk">
        <b-form-group label="New Preset Name" label-for="name-input">
          <b-form-input id="name-input" v-model="name" placeholder="Attitude/OtherRoll" required></b-form-input>
        </b-form-group>
      </form>
    </b-modal>
  </div>
</template>
<script>
import { store } from './Globals.js'
import debounce from 'v-debounce'
import ExpressionEditor from './ExpressionEditor.vue'

export default {
    name: 'PlotSetup',
    components: {
        ExpressionEditor
    },
    directives: {
        debounce
    },
    data () {
        return {
            state: store,
            name: ''
        }
    },
    computed: {
        additionalCompletionItems () {
            const additionalCompletionItems = [
                'mag_heading_df(MAG[0],ATT)',
                'mag_heading(RAW_IMU,ATTITUDE)',
                'max(x,y)',
                'min(x,y)'
            ]
            for (const name of this.state.namedFloats) {
                additionalCompletionItems.push(`named(NAMED_VALUE_FLOAT,"${name}")`)
            }
            return additionalCompletionItems
        },
        completionOptions () {
            const messageOptions = Object.keys(this.state.messageTypes).flatMap(key => {
                const fields = this.state.messageTypes[key].expressions.map(field => `${key}.${field}`)
                return [key, ...fields]
            })
            return [...this.additionalCompletionItems, ...messageOptions]
        }
    },
    methods: {
        createNewChart () {
            this.state.charts.push({
                expressions: [],
                expressionErrors: []
            })
        },
        removeChart (index) {
            this.state.charts.splice(index, 1)
        },
        createNewExpression (chartIdx) {
            this.state.plotOn = true
            const chart = this.state.charts[chartIdx]
            this.$nextTick(() => {
                chart.expressions.push({
                    name: '1+1',
                    color: this.getFirstFreeColor(chartIdx),
                    axis: this.getFirstFreeAxis(chartIdx)
                })
            })
        },
        // TODO: this is duplicated in Plotly.vue, refactor it out!
        getFirstFreeAxis (chartIdx) {
            const chart = this.state.charts[chartIdx]
            return this.state.allAxis.find(axis =>
                !chart.expressions.some(field => field.axis === axis)
            ) || this.state.allAxis[this.state.allAxis.length - 1]
        },
        getFirstFreeColor (chartIdx) {
            const chart = this.state.charts[chartIdx]
            return this.state.allColors.find(color =>
                !chart.expressions.some(field => field.color === color)
            ) || this.state.allColors[this.state.allColors.length - 1]
        },
        removePlot (chartIdx, fieldName) {
            const chart = this.state.charts[chartIdx]
            const index = chart.expressions.findIndex(e => e.name === fieldName)
            if (index !== -1) {
                chart.expressions.splice(index, 1)
            }
        },
        clearAllPlots () {
            this.state.charts.forEach(chart => {
                chart.expressions = []
                chart.expressionErrors = []
            })
        },
        savePreset (name) {
            const myStorage = window.localStorage
            const saved = JSON.parse(myStorage.getItem('savedFields')) || {}
            // For presets, we might want to save all charts or just the first one.
            // Saving all charts for now as a nested structure.
            saved[name] = this.state.charts.map(chart =>
                chart.expressions.map(field => [field.name, field.axis, field.color, field.function])
            )
            myStorage.setItem('savedFields', JSON.stringify(saved))
            this.$eventHub.$emit('presetsChanged')
        },

        resetModal () {
            this.name = ''
        },
        handleOk (bvModalEvt) {
            // Prevent modal from closing
            bvModalEvt.preventDefault()
            if (this.name.length > 0) {
                this.savePreset(this.name)

                // Hide the modal manually
                this.$nextTick(() => {
                    this.$refs.modal.hide()
                })
            }
        }
    }
}
</script>
<style>
/* MAIN */
.plot-wrapper {
  min-height: 160px;
  overflow: hidden;
  overflow-y: scroll;
}

/* COLOR PICKER */

ul.colorpicker {
  font-family: 'Montserrat', sans-serif;
}

ul.colorpicker li {
  text-align: center;
  cursor: default;
  font-size: 13px;
  padding-top: 1px;
}

ul.colorpicker li:hover {
  background-color: #1E2536;
  border-left: 3px solid #1E2536;
}

ul.colorpicker li a {
  cursor: pointer;
}

li.field {
  line-height: 26px;
  padding-left: 20px;
  font-size: 90%;
}

li.plotsetup {
  display: block;
}

i {
  margin: 5px;
  padding: 0;
}

.plotname {
  display: inline-block;
  line-height: 15px;
  margin-bottom: 0;
  font-size: 13px;
  width: 100%;
  border: 1px solid grey;
  padding: 4.5px;
  border-radius: 20px;
}

.plotname:focus {
  background-color: rgba(241, 248, 255, 0.966);
  outline: none;
}

select {
  display: inline;
  border-radius: 5px;
  border: 1px solid rgb(156, 156, 156);
  background-color: rgb(255, 255, 255);
  padding: 2px 2.5px;
  color: #838282;
}

select:focus {
  border: 1.5px solid #d47f00;
  outline: none;
}

select option {
  background-color: rgb(216, 215, 215);
}

select option:hover {
  background-color: #d47f00;
}

.fa-trash {
  margin: 12px 5px 10px 1px !important;
  font-size: 10px;
  float: right;
}

.error {
  color: red;
}

/* BUTTONS */

.btns-wrapper {
  display: flex;
  flex-flow: row wrap;
  justify-content: space-evenly;
  margin: 10px;
}

/* SAVE PRESET BUTTON */

.save-preset {
  background-color: rgb(33, 41, 61);
  color: #fff;
  border-radius: 15px;
  padding: 0px 10px 0px 0px;
  border: 1px solid rgba(91, 100, 117, 0.76);
  font-size: 13px;
}

.save-preset:hover {
  background-color: rgb(47, 58, 87);
  box-shadow: 0px 0px 12px 0px rgba(37, 78, 133, 0.55);
  transition: all 0.5s ease;
}

.save-preset:focus {
  outline: none;
}

/* ADD EXPRESSION BUTTON */

.add-expression {
  background-color: rgb(33, 41, 61);
  color: #fff;
  border-radius: 15px;
  padding: 0px 10px 0px 0px;
  border: 1px solid rgba(91, 100, 117, 0.76);
  font-size: 13px;
}

.add-expression:hover {
  background-color: rgb(47, 58, 87);
  box-shadow: 0px 0px 12px 0px rgba(37, 78, 133, 0.55);
  transition: all 0.5s ease;
}

.add-expression:focus {
  outline: none;
}

/* MEDIA QUERIES */

@media (min-width: 1000px) and (max-width: 1440px) {
  p.plotname {
    width: 55%;
  }
}

@media (min-width: 2000px) {
  p.plotname {
    width: 60%;
  }
}
</style>
<style scoped>
.chart-setup-area {
  border-bottom: 1px solid #434b52da;
  padding-bottom: 10px;
  margin-bottom: 10px;
}

.chart-header {
  padding: 5px 20px;
  background-color: #1e2536;
  font-weight: bold;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.remove-button-chart {
  color: #ff4d4d;
  cursor: pointer;
}

.plot-wrapper-inner {
  max-height: 150px;
  overflow-y: auto;
}

.global-btns {
  border-top: 2px solid #5b6475;
  padding-top: 10px;
}

.add-chart {
  background-color: #2d3a57;
  color: #fff;
  border-radius: 15px;
  padding: 5px 15px;
  border: 1px solid #5b6475;
  font-size: 13px;
  margin-bottom: 5px;
}

.add-chart:hover {
  background-color: #3e4e73;
}
</style>
