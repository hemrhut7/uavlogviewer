<template>
    <div v-if="hasMessages">

        <!--<li v-if="state.plotOn" @click="state.plotOn=!state.plotOn">-->
        <!--<a class="section">-->
        <!--<i class="fas fa-eye-slash fa-lg"></i> Toggle Plot</a>-->
        <!--</li>-->
        <tree-menu
            v-if="Object.keys(availableMessagePresets).length > 0"
            :nodes="availableMessagePresets"
            :label="'Presets'"
            :clean-name="'Presets'"
            :level="0">

        </tree-menu>
        <li v-b-toggle="'messages'">
            <a class="section">
                Plot Individual Field
                <i class="fas fa-caret-down"></i></a>
        </li>

        <b-collapse id="messages">
            <li class="input-li">
                <input id="filterbox" placeholder=" Type here to filter..." v-model="filter">
            </li>
            <div v-for="(log, logIdx) in state.logs" :key="'log-messages-' + logIdx" class="log-messages-group">
                <div
                    class="log-header type"
                    @click="toggleLog(logIdx)"
                    style="cursor: pointer; display: flex; justify-content: space-between; align-items: center;">
                    <i class="fas fa-file-alt"></i> {{ log.filename }}
                    <i class="expand fas" :class="(logVisible[logIdx] !== false) ? 'fa-caret-up' : 'fa-caret-down'"></i>
                </div>
                <div
                    v-if="logVisible[logIdx] !== false"
                    class="log-offset-control"
                    style="padding: 10px; background: rgba(0,0,0,0.1); border-bottom: 1px solid rgba(255,255,255,0.05);"
                >
                    <div
                        style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;"
                    >
                        <span style="font-size: 11px; color: #aaa;">Align Offset:</span>
                        <span style="font-size: 11px; color: #64e9ff; font-family: monospace;">
                            {{ (log.offset || 0).toFixed(1) }}s
                        </span>
                    </div>
                    <input
                        type="range"
                        min="-300"
                        max="300"
                        step="0.1"
                        v-model.number="log.offset"
                        @input="onOffsetChange"
                        style="width: 100%; height: 4px; margin: 0; cursor: pointer;"
                    >
                </div>
                <b-collapse :visible="logVisible[logIdx] !== false">
                <template v-for="key of Object.keys(logMessageTypesFiltered(logIdx)).sort()">
                    <li class="type" v-bind:key="logIdx + '-' + key">
                        <div
                            v-b-toggle="'type' + logIdx + '-' + key"
                            :title="messageDocs[key.split('[')[0]] ? messageDocs[key.split('[')[0]].doc : ''"
                        >
                            <a class="section">{{key}} <span v-if="log.messageTypes[key].isArray">{{"[...]"}}</span>
                                <i class="expand fas fa-caret-down"></i>
                                <span class="description">
                                  {{ messageDocs[key.split('[')[0]] ? messageDocs[key.split('[')[0]].doc : '' }}
                                </span>
                            </a>
                        </div>
                    </li>
                    <b-collapse
                        :id="'type' + logIdx + '-' + key"
                        v-bind:key="logIdx + '-' + key + '1'"
                        v-model="expandedTypes[logIdx + '-' + key]">
                        <template v-for="item in log.messageTypes[key].complexFields">
                            <li @click="toggle(logIdx, key, item.name, 0)"
                                class="field"
                                :title="messageDocs[key] ? messageDocs[key][item.name] : ''"
                                v-bind:key="logIdx + '-' + key + '.' + item.name"
                                v-if="isPlottable(logIdx, key, item.name)
                                    && item.name.toLowerCase().indexOf(filter.toLowerCase()) !== -1">
                                <div class="field-content">
                                    <a> {{item.name}}
                                        <span v-if="item.units!=='?' && item.units!==''"> ({{item.units}})</span>
                                    </a>
                                    <span class="description">
                                      {{ messageDocs[key] ? messageDocs[key][item.name.split('[')[0]] : '' }}
                                    </span>
                                </div>

                                <div class="chart-indicators" v-if="state.charts.length > 1">
                                    <span v-for="(chart, idx) in state.charts"
                                          :key="'chart-btn-' + idx"
                                          class="chart-btn"
                                          :class="{ active: isPlottedInChart(logIdx, key, item.name, idx) }"
                                          @click.stop="toggle(logIdx, key, item.name, idx)"
                                          :title="'Toggle on Chart ' + (idx + 1)">
                                        {{ idx + 1 }}
                                    </span>
                                </div>

                                <a @click.stop="toggle(logIdx, key, item.name)"
                                   v-if="state.charts.length === 1 && isPlotted(logIdx, key, item.name)"
                                   class="remove-container">
                                    <i class="remove-icon fas fa-trash" title="Remove from all charts"></i>
                                </a>
                            </li>
                        </template>
                    </b-collapse>
                </template>
                </b-collapse>
            </div>
        </b-collapse>
    </div>
</template>
<script>
import { isArray } from 'underscore'
import { store } from './Globals.js'
import TreeMenu from './widgets/TreeMenu.vue'
import fastXmlParser from 'fast-xml-parser'

export default {
    name: 'message-menu',
    components: { TreeMenu },
    data () {
        return {
            filter: '',
            checkboxes: {},
            expandedTypes: {},
            logVisible: {},
            state: store,
            messages: {},
            messageTypes: [],
            hiddenTypes: [
                'MISSION_CURRENT',
                'SYSTEM_TIME', 'HEARTBEAT', 'STATUSTEXT',
                'COMMAND_ACK', 'PARAM_VALUE', 'AUTOPILOT_VERSION',
                'TIMESYNC', 'MISSION_COUNT', 'MISSION_ITEM_INT',
                'MISSION_ITEM', 'MISSION_ITEM_REACHED', 'MISSION_ACK',
                'HOME_POSITION',
                'STRT',
                'FMT',
                'PARM',
                'MSG',
                'FMTU',
                'UNIT',
                'MULT'
            ],
            // TODO: lists are nor clear, use objects instead
            messagePresets: {
            },
            userPresets: {},
            messageDocs: {}
        }
    },
    created () {
        this.$eventHub.$on('messageTypes', this.handleMessageTypes)
        this.$eventHub.$on('presetsChanged', this.loadLocalPresets)
        this.messagePresets = this.loadXmlPresets()
        this.messageDocs = this.loadXmlDocs()
        this.loadLocalPresets()
    },
    beforeDestroy () {
        this.$eventHub.$off('messageTypes')
    },
    methods: {
        toggleLog (logIdx) {
            if (this.logVisible[logIdx] === undefined) {
                this.$set(this.logVisible, logIdx, false)
            } else {
                this.$set(this.logVisible, logIdx, !this.logVisible[logIdx])
            }
        },
        onOffsetChange () {
            this.$eventHub.$emit('recalc-plots')
        },

        loadXmlPresets () {
            // eslint-disable-next-line
            const graphs = {}
            const files = [
                require('../assets/mavgraphs.xml'),
                require('../assets/mavgraphs2.xml'),
                require('../assets/ekfGraphs.xml'),
                require('../assets/ekf3Graphs.xml')
            ]
            for (const contents of files) {
                const result = fastXmlParser.parse(contents.default, { ignoreAttributes: false })
                const igraphs = result.graphs
                for (const graph of igraphs.graph) {
                    let i = ''
                    const name = graph['@_name']
                    if (!Array.isArray(graph.expression)) {
                        graph.expression = [graph.expression]
                    }
                    for (const expression of graph.expression) {
                        const fields = []
                        for (let exp of expression.split(' ')) {
                            if (exp.indexOf(':') >= 0) {
                                exp = exp.replace(':2', '')
                                fields.push([exp, 1])
                            } else {
                                fields.push([exp, 0])
                            }
                        }
                        graphs[name + i] = fields
                        // workaround to avoid replacing a key
                        // TODO: implement this in a way that doesn't need this hack
                        i += ' '
                    }
                }
            }
            return graphs
        },
        loadLocalPresets () {
            const saved = window.localStorage.getItem('savedFields')
            if (saved !== null) {
                this.userPresets = JSON.parse(saved)
                for (const preset in this.userPresets) {
                    for (const message in this.userPresets[preset]) {
                        // Field 3 means it is a user preset and can be deleted
                        this.userPresets[preset][message][3] = 1
                    }
                }
            }
        },
        loadXmlDocs () {
            const logDocs = {}
            const files = [
                require('../assets/logmetadata/plane.xml'),
                require('../assets/logmetadata/copter.xml'),
                require('../assets/logmetadata/tracker.xml'),
                require('../assets/logmetadata/rover.xml')
            ]
            for (const contents of files) {
                const result = fastXmlParser.parse(contents.default, { ignoreAttributes: false })
                const igraphs = result.loggermessagefile
                for (const graph of igraphs.logformat) {
                    logDocs[graph['@_name']] = { doc: graph.description }
                    if (!isArray(graph.fields.field)) {
                        continue
                    }
                    for (const field of graph.fields.field) {
                        logDocs[graph['@_name']][field['@_name']] = field.description
                    }
                }
            }
            return logDocs
        },
        handleMessageTypes (messageTypes, logIndex) {
            if (this.$route.query.plots) {
                this.state.plotOn = true
            }
        },
        getFullname (logIdx, message, field) {
            if (logIdx === 0) return message + '.' + field
            return `[${logIdx}]${message}.${field}`
        },
        isPlotted (logIdx, message, field) {
            const fullname = this.getFullname(logIdx, message, field)
            return this.state.charts.some(chart =>
                chart.expressions.some(e => e.name === fullname)
            )
        },
        isPlottedInChart (logIdx, message, field, chartIdx) {
            const fullname = this.getFullname(logIdx, message, field)
            const chart = this.state.charts[chartIdx]
            if (!chart) return false
            return chart.expressions.some(e => e.name === fullname)
        },
        toggle (logIdx, message, item, chartIdx) {
            this.state.plotOn = true
            const fullname = this.getFullname(logIdx, message, item)
            this.$nextTick(function () {
                this.$eventHub.$emit('togglePlot', fullname, undefined, undefined, chartIdx)
            })
        },
        logMessageTypesFiltered (logIdx) {
            const log = this.state.logs[logIdx]
            if (!log || !log.messageTypes) return {}
            const filtered = {}
            for (const key of Object.keys(log.messageTypes)) {
                if (this.hiddenTypes.indexOf(key) === -1) {
                    if (this.filter === '') {
                        filtered[key] = log.messageTypes[key]
                        continue
                    }
                    if (log.messageTypes[key].expressions
                        .filter(field => field.toLowerCase().indexOf(this.filter.toLowerCase()) !== -1).length > 0) {
                        filtered[key] = log.messageTypes[key]
                    }
                }
            }
            return filtered
        },
        isAvailable (msg, logIdx = 0) {
            const msgRe = /[A-Z][A-Z0-9_]+(\[[0-9]\])?(\.[a-zA-Z0-9_]+)?/g
            const match = msg[0].match(msgRe)
            if (!match) return true
            const log = this.state.logs[logIdx]
            if (!log || !log.messageTypes) return false

            const msgName = match[0].split('.')[0]
            if (!log.messageTypes[msgName]) return false

            const fieldName = match[0].split('.')[1]
            if (fieldName === undefined) return true

            if (log.messageTypes[msgName].expressions.indexOf(fieldName) < 0) {
                return false
            }
            return true
        },
        isPlottable (logIdx, message, field) {
            const log = this.state.logs[logIdx]
            if (!log || !log.messageTypes || !log.messageTypes[message]) return false
            // For now assume all fields in complexFields are plottable if they exist
            return true
        }
    },
    computed: {

        hasMessages () {
            return this.state.logs.some(log => log.messageTypes && Object.keys(log.messageTypes).length > 0)
        },
        availableMessagePresets () {
            const dict = {}
            // do it for default messages
            for (const [key, value] of Object.entries(this.messagePresets)) {
                let missing = false
                let color = 0
                for (const field of value) {
                    // If all of the expressions match, add this and move on
                    if (field[0] === '') {
                        continue
                    }
                    missing = missing || !this.isAvailable(field, 0)
                    if (!missing) {
                        if (!(key in dict)) {
                            dict[key] = { messages: [[...field, color++]] }
                        } else {
                            dict[key].messages.push([...field, color++])
                        }
                    }
                }
                if (missing) {
                    delete dict[key]
                }
            }
            // And again for user presets
            for (const [key, value] of Object.entries(this.userPresets)) {
                let missing = false
                let color = 0
                for (const field of value) {
                    // If all of the expressions match, add this and move on
                    missing = missing || !this.isAvailable(field, 0)
                    if (!missing) {
                        if (!(key in dict)) {
                            dict[key] = { messages: [[...field, color++]] }
                        } else {
                            dict[key].messages.push([...field, color++])
                        }
                    }
                }
            }
            const newDict = {}
            for (const [key, value] of Object.entries(dict)) {
                let current = newDict
                const fields = key.trim().split('/')
                const lastField = fields.pop()
                for (const field of fields) {
                    if (!(field in current)) {
                        console.log('overwriting ' + field)
                        current[field] = {}
                    }
                    current = current[field]
                }
                current[lastField] = value
            }
            return newDict
        }
    }
}
</script>
<style scoped>
    i {
        margin: 5px;
    }
    i.expand {
        float: right;
    }
    li > div {
        display: inline-block;
        width: 100%;
    }
    li.field {
        line-height: 29px;
        padding-left: 40px;
        font-size: 90%;
        display: inline-block;
        vertical-align: middle;
        width: 100%;
    }
    li.type {
        line-height: 30px;
        padding-left: 10px;
        font-size: 85%;
    }
    .log-header {
        padding: 8px 10px;
        background: rgba(100, 233, 255, 0.1);
        color: #64e9ff;
        font-weight: bold;
        font-size: 12px;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        margin-top: 5px;
    }
    i {
        margin: 5px;
    }
    i.expand {
        float: right;
    }
    li > div {
        display: inline-block;
        width: 100%;
    }
    li.field {
        line-height: 29px;
        padding-left: 40px;
        font-size: 90%;
        display: inline-block;
        vertical-align: middle;
        width: 100%;
    }
    li.type {
        line-height: 30px;
        padding-left: 10px;
        font-size: 85%;
    }
    input {
        margin: 12px 12px 15px 10px;
        border: 2px solid #ccc;
        -webkit-border-radius: 4px;
        -moz-border-radius: 4px;
        border-radius: 4px;
        background-color: rgba(255, 255, 255, 0.897);
        color: rgb(51, 51, 51);
        width: 92%;
    }
    input:focus {
        outline: none;
        border: 2px solid #135388;
    }
    .input-li:hover {
        background-color: rgba(30, 37, 54, 0.205);
        border-left: 3px solid rgba(24, 30, 44, 0.212);
    }
    ::placeholder { /* Chrome, Firefox, Opera, Safari 10.1+ */
        color: rgb(148, 147, 147);
        opacity: 1; /* Firefox */
    }
    :-ms-input-placeholder { /* Internet Explorer 10-11 */
        color: #2e2e2e;
    }
    ::-ms-input-placeholder { /* Microsoft Edge */
        color: #2e2e2e;
    }
    li.field {
        padding: 4px 5px 4px 30px;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .field-content {
        flex-grow: 1;
        width: auto !important;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    i.remove-icon {
        margin-left: 10px;
    }
    .remove-container {
        display: flex;
        align-items: center;
    }

    .chart-indicators {
        display: flex;
        gap: 4px;
        margin-left: 5px;
        flex-shrink: 0;
        width: auto !important;
    }

    .chart-btn {
        display: inline-block;
        width: 18px;
        height: 18px;
        line-height: 16px;
        text-align: center;
        border: 1px solid #777;
        border-radius: 3px;
        font-size: 11px;
        cursor: pointer;
        background: #3a3a3a;
        color: #fff;
        font-weight: bold;
        transition: all 0.2s;
    }

    .chart-btn:hover {
        background: #555;
        border-color: #999;
    }

    .chart-btn.active {
        background: #2196F3;
        color: white;
        border-color: #4dabf5;
        box-shadow: 0 0 8px rgba(33, 150, 243, 0.6);
    }

    @media (min-width: 575px) and (max-width: 992px) {
       a {
        padding: 2px 60px 2px 55px !important;
       }
    }

    span.description {
      opacity: 70%;
      font-size: 80%;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      display: inline-block;
      max-width: 180px;
      vertical-align: top;
    }

</style>
