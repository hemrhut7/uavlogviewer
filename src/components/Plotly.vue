<template>
    <div :id="'plot-' + chartIndex" ref="line" style="width:100%;height: 100%"></div>
</template>

<script>
import Plotly from 'plotly.js'
import { store } from './Globals.js'
import * as d3 from 'd3'
import { faWindowRestore } from '@fortawesome/free-solid-svg-icons'
import Vue from 'vue'
import { isNumber } from 'underscore'

const timeformat = ':02,2f'

const plotOptions = {
    legend: {
        x: 0.1,
        y: 1,
        traceorder: 'normal',
        borderwidth: 1
    },
    showlegend: true,
    // eslint-disable-next-line
    plot_bgcolor: '#f8f8f8',
    // eslint-disable-next-line
    paper_bgcolor: 'white',
    // autosize: true,
    margin: { t: 20, l: 0, b: 30, r: 10 },
    xaxis: {
        title: 'Time since boot',
        domain: [0.15, 0.85],
        rangeslider: {},
        tickformat: timeformat
    },
    yaxis: {
        // title: 'axis1',
        titlefont: {
            color: '#1f77b4'
        },
        tickfont: {
            color: '#1f77b4', size: 12
        },
        anchor: 'free',
        position: 0.03,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    },
    yaxis2: {
        // title: 'yaxis2 title',
        titlefont: { color: '#ff7f0e' },
        tickfont: { color: '#ff7f0e', size: 12 },
        anchor: 'free',
        overlaying: 'y',
        side: 'left',
        position: 0.07,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    },
    yaxis3: {
        // title: 'yaxis4 title',
        titlefont: { color: '#2ca02c' },
        tickfont: { color: '#2ca02c' },
        anchor: 'free',
        overlaying: 'y',
        side: 'left',
        position: 0.11,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    },
    yaxis4: {
        // title: 'yaxis5 title',
        titlefont: { color: '#d62728' },
        tickfont: { color: '#d62728' },
        anchor: 'free',
        overlaying: 'y',
        side: 'left',
        position: 0.92,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    },
    yaxis5: {
        // title: 'yaxis5 title',
        titlefont: { color: '#9467BD' },
        tickfont: { color: '#9467BD' },
        anchor: 'free',
        overlaying: 'y',
        side: 'left',
        position: 0.96,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    },
    yaxis6: {
        // title: 'yaxis5 title',
        titlefont: { color: '#8C564B' },
        tickfont: { color: '#8C564B' },
        anchor: 'free',
        overlaying: 'y',
        side: 'left',
        position: 1.0,
        autotick: true,
        showline: true,
        ticklen: 3,
        tickangle: 45
    }

}

export default {
    created () {
        this.$eventHub.$on('cesium-time-changed', this.setCursorTime)
        this.$eventHub.$on('hoveredTime', this.setCursorTime)
        this.$eventHub.$on('force-resize-plotly', this.resize)
        this.$eventHub.$on('child-zoomed', this.onTimeRangeChanged)
        this.$eventHub.$on('recalc-stats', this.addMaxMinMeanToTitles)
        this.$eventHub.$on('recalc-plots', this.plot)
        this.zoomInterval = null
    },
    mounted () {
        const WIDTH_IN_PERCENT_OF_PARENT = 90
        d3.select(this.$refs.line)
            .append('div')
            .style({
                width: '100%',
                'margin-left': (100 - WIDTH_IN_PERCENT_OF_PARENT) / 2 + '%',
                height: '100%'
            })

        this.gd = this.$refs.line
        const _this = this
        this.$nextTick(function () {
            if (this.$route.query.ranges) {
                const ranges = []
                for (const field of this.$route.query.ranges.split(',')) {
                    ranges.push(parseFloat(field))
                }
                if (ranges.length > 0) {
                    plotOptions.xaxis.range = [ranges[0], ranges[1]]
                }
                if (ranges.length >= 4) {
                    plotOptions.yaxis.range = [ranges[2], ranges[3]]
                }
                if (ranges.length >= 6) {
                    plotOptions.yaxis2.range = [ranges[4], ranges[5]]
                }
                if (ranges.length >= 8) {
                    plotOptions.yaxis3.range = [ranges[6], ranges[7]]
                }
                if (ranges.length >= 10) {
                    plotOptions.yaxis4.range = [ranges[8], ranges[9]]
                }
            }
            if (this.$route.query.plots) {
                for (const field of this.$route.query.plots.split(',')) {
                    _this.addPlots([field])
                }
            }
        })
        this.instruction = ''
        this.$eventHub.$on('togglePlot', this.togglePlot)
        this.$eventHub.$on('addPlots', this.addPlots)
        this.$eventHub.$on('plot', this.plot)
        this.$eventHub.$on('clearPlot', this.clearPlot)
    },
    beforeDestroy () {
        this.$eventHub.$off('animation-changed')
        this.$eventHub.$off('cesium-time-changed', this.setCursorTime)
        this.$eventHub.$off('hoveredTime', this.setCursorTime)
        this.$eventHub.$off('force-resize-plotly', this.resize)
        this.$eventHub.$off('child-zoomed', this.onTimeRangeChanged)
        this.$eventHub.$off('recalc-stats', this.addMaxMinMeanToTitles)
        this.$eventHub.$off('recalc-plots', this.plot)
        this.$eventHub.$off('addPlots', this.addPlots)
        this.$eventHub.$off('plot', this.plot)
        this.$eventHub.$off('clearPlot', this.clearPlot)
        this.$eventHub.$off('togglePlot', this.togglePlot)
        clearInterval(this.interval)
    },
    props: {
        chartIndex: {
            type: Number,
            default: 0
        }
    },
    data () {
        return {
            gd: null,
            plotInstance: null,
            state: store
        }
    },
    methods: {
        popupButton () {
            return {
                name: 'Open in new window',
                icon: {
                    title: 'test',
                    name: 'iconFS',
                    width: 600,
                    height: 600,
                    path: faWindowRestore.icon[4]
                }, // Use any icon available
                click: (gd) => {
                    const newWindow = window.open(
                        '/#/plot', '_blank',
                        'toolbar=no,scrollbars=yes,resizable=yes,top=500,left=500,width=800,height=400,allow-scripts'
                    )
                    const externalPlotInterval = setInterval(() => {
                        try {
                            newWindow.setPlotData(gd.data)
                            newWindow.setPlotOptions(gd.layout)
                            newWindow.setCssColors(this.state.cssColors)
                            newWindow.setFlightModeChanges(this.state.flightModeChanges)
                            newWindow.setEventHub(this.$eventHub)
                            newWindow.plot()
                            clearInterval(externalPlotInterval)
                        } catch (e) {
                            console.log(e)
                        }
                    }, 1000)
                    this.state.childPlots.push(newWindow)
                }
            }
        },
        csvButton () {
            return {
                name: 'downloadCsv',
                title: 'Download data as csv',
                icon: Plotly.Icons.disk,
                click: () => {
                    const data = this.gd.data
                    const header = ['timestamp(ms)']
                    for (const series of data) {
                        header.push(series.name.split(' |')[0])
                    }

                    const indexes = []

                    const interval = 100
                    let currentTime = Infinity
                    let finaltime = 0

                    for (const series in data) {
                        indexes.push(0)
                        const x = data[series].x
                        currentTime = Math.min(currentTime, x[0])
                        finaltime = Math.max(finaltime, x[x.length - 1])
                    }
                    finaltime = Math.min(finaltime, this.state.timeRange[1])
                    currentTime = Math.max(currentTime, this.state.timeRange[0])
                    const csv = [header.map(e => e.replace(',', ';'))]
                    while (currentTime < finaltime - interval) {
                        const line = [currentTime]
                        for (const series in data) {
                            let index = indexes[series]
                            let x = data[series].x[index]
                            while (x < currentTime) {
                                indexes[series] += 1
                                index = indexes[series]
                                x = data[series].x[index]
                            }
                            const y = data[series].y[index]
                            const prevX = data[series].x[index - 1]
                            const prevY = data[series].y[index - 1]
                            const interpolatedY = this.interpolateY(prevY, y, prevX, x, currentTime)
                            line.push(interpolatedY)
                        }
                        csv.push(line)
                        currentTime = currentTime + interval
                    }
                    const csvContent = csv.map(e => e.join(',')).join('\n')
                    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
                    const link = document.createElement('a')
                    const url = URL.createObjectURL(blob)
                    link.setAttribute('href', url)
                    link.setAttribute('download', 'data.csv')
                    link.style.visibility = 'hidden'
                    document.body.appendChild(link)
                    link.click()
                    document.body.removeChild(link)
                }
            }
        },
        interpolateY (y1, y2, x1, x2, x) {
            const dx = x2 - x1
            if (dx <= 0) {
                throw new Error('x2 must be greater than x1')
            }
            const dy = y2 - y1
            const slope = dy / dx
            const interpolatedY = y1 + slope * dx
            return interpolatedY
        },
        resize () {
            Plotly.Plots.resize(this.gd)
        },
        waitForMessages (messages) {
            // Updated to check messages across all logs
            for (const message of messages) {
                this.$eventHub.$emit('loadType', message)
            }
            let interval
            const _this = this
            let counter = 0
            return new Promise((resolve, reject) => {
                interval = setInterval(function () {
                    for (const message of messages) {
                        const [logIdx, msgName] = _this.parseLogIndex(message)
                        const log = _this.state.logs[logIdx]
                        if (!log || !log.messages[msgName]) {
                            counter += 1
                            if (counter > 30) {
                                clearInterval(interval)
                                reject(new Error(`Could not load messageType ${message}`))
                            }
                            return
                        }
                    }
                    clearInterval(interval)
                    resolve()
                }, 300)
            })
        },
        onRangeChanged (event) {
            this.addMaxMinMeanToTitles()
            if (event !== undefined && this.state.syncZoom) {
                if (event['xaxis.range']) {
                    this.state.timeRange = event['xaxis.range']
                    this.updatChildrenTimeRange(this.state.timeRange)
                }
                if (event['xaxis.range[0]']) {
                    this.state.timeRange = [event['xaxis.range[0]'], event['xaxis.range[1]']]
                    this.updatChildrenTimeRange(this.state.timeRange)
                }
                if (event['xaxis.autorange']) {
                    this.state.timeRange = [this.gd.layout.xaxis.range[0], this.gd.layout.xaxis.range[1]]
                    this.updatChildrenTimeRange(this.state.timeRange)
                }
            }
        },

        onTimeRangeChanged (timeRange) {
            this.state.timeRange = timeRange
            this.updatChildrenTimeRange(this.state.timeRange)
        },
        updatChildrenTimeRange (timeRange) {
            for (const child of this.state.childPlots) {
                child.setTimeRange(timeRange)
            }
        },
        addMaxMinMeanToTitles   () {
            const average = arr => arr.length > 0 ? arr.reduce((p, c) => p + c, 0) / arr.length : 0
            const gd = this.gd
            const xRange = gd.layout.xaxis.range

            let needsRelayout = false

            gd.data.forEach(trace => {
                let yInside = []

                if (this.state.statsFullRange) {
                    yInside = trace.y.filter(val => val !== null && !isNaN(val))
                } else {
                    const len = Math.min(trace.x.length, trace.y.length)
                    for (let i = 0; i < len; i++) {
                        const x = trace.x[i]
                        const y = trace.y[i]

                        if (x > xRange[0] && x < xRange[1] && y !== null && !isNaN(y)) {
                            yInside.push(y)
                        }
                    }
                }

                if (yInside.length === 0) return

                const mean = average(yInside)
                const variance = yInside.reduce((p, c) => p + Math.pow(c - mean, 2), 0) / yInside.length
                const std = Math.sqrt(variance)

                const extraData = ` | Min: ${Math.min(...yInside).toFixed(2)} \
Max: ${Math.max(...yInside).toFixed(2)} \
Mean: ${mean.toFixed(2)} \
Std: ${std.toFixed(2)}`

                if (trace.name.indexOf(' | ') === -1 || trace.name.split(' | ')[1] !== extraData.substring(3)) {
                    trace.name = trace.name.split(' | ')[0] + extraData
                    needsRelayout = true
                }
            })
            if (needsRelayout) {
                Plotly.relayout(this.gd, this.gd.layout)
            }
        },
        isPlotted (fieldname) {
            for (const field of this.chart.expressions) {
                if (field.name === fieldname) {
                    return true
                }
            }
            return false
        },
        getFirstFreeAxis () {
            for (const i of this.state.allAxis) {
                let taken = false
                for (const field of this.chart.expressions) {
                    if (field.axis === i) {
                        taken = true
                    }
                }
                if (!taken) {
                    return i
                }
            }
            return this.state.allAxis.length - 1
        },
        getFirstFreeColor () {
            for (const i of this.state.allColors) {
                let taken = false
                for (const field of this.chart.expressions) {
                    if (field.color === i) {
                        taken = true
                    }
                }
                if (!taken) {
                    return i
                }
            }
            return this.state.allColors[this.state.allColors.length - 1]
        },
        createNewField (fieldname, axis, color) {
            if (color === undefined) {
                color = this.getFirstFreeColor()
            } else if (!isNaN(color)) {
                color = this.state.allColors[color]
            }
            if (axis === undefined) {
                axis = this.getFirstFreeAxis()
            }
            return {
                name: fieldname,
                color: color,
                axis: axis
            }
        },

        addPlots (plots, targetChartIndex) {
            if (targetChartIndex !== undefined && targetChartIndex !== this.chartIndex) {
                return
            }
            this.state.plotLoading = true
            const requested = new Set()
            for (const plot of plots) {
                const expression = plot[0]
                const messages = this.findMessagesInExpression(expression)
                if (messages !== null) {
                    for (const [msgWithPrefix] of messages) {
                        const [logIdx, msgName] = this.parseLogIndex(msgWithPrefix)
                        const log = this.state.logs[logIdx]
                        if (!log || !(msgName in log.messages)) {
                            if (requested.has(msgWithPrefix)) continue
                            requested.add(msgWithPrefix)
                        }
                    }
                }
            }
            if ([...requested].length > 0) {
                this.waitForMessages([...requested]).then(() => {
                    this.addPlots(plots, targetChartIndex)
                })
                    .catch((e) => {
                        alert(e)
                        this.plot()
                    })
                return
            }
            const newplots = []
            for (const plot of plots) {
                const expression = plot[0]
                const axis = plot[1]
                const color = plot[2]
                if (!this.isPlotted(expression)) {
                    newplots.push(this.createNewField(expression, axis, color))
                }
            }
            this.chart.expressions.push(...newplots)
            this.plot()
        },
        removePlot (fieldname) {
            const index = this.chart.expressions.indexOf(fieldname)
            if (index !== -1) {
                this.chart.expressions.splice(index, 1)
            }
            this.plot()
            this.onRangeChanged()
        },
        clearPlot () {
            while (this.chart.expressions.length) {
                this.chart.expressions.pop()
            }
        },
        resetAxis (index) {
            let suffix = ''
            suffix = index === 0 ? suffix : parseInt(index) + 1
            const key = 'yaxis' + suffix
            const obj = {}
            obj[key] = plotOptions[key]
            obj[key].autorange = true
            Plotly.relayout(this.gd, obj)
        },
        togglePlot (fieldname, axis, color, targetChartIndex) {
            if (targetChartIndex !== undefined && targetChartIndex !== this.chartIndex) {
                return
            }
            if (this.isPlotted((fieldname))) {
                let index
                for (const i in this.chart.expressions) {
                    if (this.chart.expressions[i].name === fieldname) {
                        index = i
                    }
                }
                this.resetAxis(this.chart.expressions[index].axis)
                this.chart.expressions.splice(index, 1)
                this.plot()
                this.onRangeChanged()
            } else {
                this.addPlots([[fieldname, axis, color]], targetChartIndex)
            }
        },
        calculateXAxisDomain () {
            let start = 0.02
            let end = 0.98
            for (const field of this.chart.expressions) {
                if (field.axis === 0) start = Math.max(start, 0.03)
                else if (field.axis === 1) start = Math.max(start, 0.07)
                else if (field.axis === 2) start = Math.max(start, 0.11)
                else if (field.axis === 5) end = Math.min(end, 0.96)
                else if (field.axis === 4) end = Math.min(end, 0.92)
                else if (field.axis === 3) end = Math.min(end, 0.88)
            }
            return [start, end]
        },
        getAxisTitle (fieldAxis) {
            const names = []
            for (const field of this.chart.expressions) {
                if (field.axis === fieldAxis) names.push(field.name)
            }
            return names.join(', ')
        },
        parseLogIndex (msgWithPrefix) {
            const match = msgWithPrefix.match(/^\[(?<index>[0-9]+)\](?<message>.+)$/)
            if (match) {
                return [parseInt(match.groups.index), match.groups.message]
            }
            return [0, msgWithPrefix] // Default to log 0
        },
        findMessagesInExpression (expression) {
            const RE = /(?<prefix>\[[0-9]+\])?(?<message>[A-Z][A-Z0-9_]+(\[[A-Za-z0-9_.]+\])?)(\.(?<field>[A-Za-z0-9_]+))?/g
            const match = []
            for (const m of expression.matchAll(RE)) {
                const prefix = m.groups.prefix || ''
                match.push([prefix + m.groups.message, m.groups.field])
            }
            return match
        },
        expressionCanBePlotted (expression, reask = false) {
            const messages = this.findMessagesInExpression(expression.name)
            if (messages === null) return [true, '']
            for (const [msgWithPrefix, field] of messages) {
                const [logIdx, msgName] = this.parseLogIndex(msgWithPrefix)
                const log = this.state.logs[logIdx]
                if (!log) return [false, `invalid log index: ${logIdx}`]
                if (!(msgName in log.messages)) {
                    if (reask) this.$eventHub.$emit('loadType', msgWithPrefix)
                    return [false, `invalid message: ${msgName}`]
                }
                if (field !== undefined) {
                    if (field !== 'time_boot_ms' && log.messageTypes[msgName].expressions.indexOf(field) < 0) {
                        return [false, `invalid field: ${msgName}.${field}`]
                    }
                }
            }
            return [true, '']
        },
        evaluateExpression (expression1) {
            if (expression1 in this.state.plotCache) return this.state.plotCache[expression1]

            const messagesWithFields = this.findMessagesInExpression(expression1)
            const fields = messagesWithFields.map(f => f[0])

            let x
            if (fields.length > 0) {
                const [logIdx, msgName] = this.parseLogIndex(fields[0])
                const log = this.state.logs[logIdx]
                if (!log || !log.messages[msgName]) return { error: 'message ' + fields[0] + ' not found' }
                x = log.messages[msgName].time_boot_ms
            } else {
                // Fallback for expressions without messages
                const log = this.state.logs[0] || this.state
                try {
                    x = log.messages.ATT.time_boot_ms
                } catch {
                    x = [0]
                }
            }

            const timeIndexes = new Array(fields.length).fill(0)
            const y = []
            let expression = expression1
            for (let i = 0; i < fields.length; i++) {
                const escapedField = fields[i].replace('[', '\\[').replace(']', '\\]')
                const regex = new RegExp(escapedField + '(\\b|\\.)', 'g')
                expression = expression.replace(regex, (match) => {
                    return match.replace(fields[i], 'a[' + i + ']')
                })
            }

            let f
            try {
                // eslint-disable-next-line
                f = new Function('a', 'return ' + expression)
            } catch (e) {
                return { error: e }
            }

            for (const time of x) {
                const vals = []
                for (let i = 0; i < fields.length; i++) {
                    const [logIdx, msgName] = this.parseLogIndex(fields[i])
                    const log = this.state.logs[logIdx]
                    const msgData = log.messages[msgName]
                    while (msgData.time_boot_ms[timeIndexes[i]] < time) {
                        timeIndexes[i] += 1
                    }
                    const newobj = {}
                    for (const key of Object.keys(msgData)) {
                        newobj[key] = msgData[key][timeIndexes[i]]
                    }
                    vals.push(newobj)
                }
                try {
                    const val = f(vals)
                    if (val !== null && isNumber(val)) y.push(val)
                    else if (val === null) y.push(null)
                } catch (e) {
                    y.push(null)
                }
            }

            const data = this.addGaps({ x: x, y: y })
            Vue.set(this.state.plotCache, expression1, data)
            this.cleanupCache()
            return data
        },
        cleanupCache () {
            const keys = Object.keys(this.state.plotCache)
            for (const key of keys) {
                const isExpressionInAnyChart = this.state.charts.some(chart =>
                    chart.expressions.some(e => e.name === key)
                )
                if (!isExpressionInAnyChart) delete this.state.plotCache[key]
            }
        },
        addGaps (data) {
            const newData = { x: [], y: [], isSwissCheese: false }
            let lastx = data.x[0]
            for (let i = 0; i < data.x.length; i++) {
                if ((data.x[i] - lastx) > 3000) {
                    newData.x.push(data.x[i] - 1)
                    newData.y.push(null)
                }
                newData.x.push(data.x[i])
                newData.y.push(data.y[i])
                lastx = data.x[i]
            }
            return newData
        },
        plot () {
            this.state.plotLoading = true
            const data = []
            const layout = JSON.parse(JSON.stringify(plotOptions))
            layout.xaxis.domain = this.calculateXAxisDomain()
            layout.xaxis.range = this.state.timeRange || undefined

            for (const field of this.chart.expressions) {
                const result = this.evaluateExpression(field.name)
                if (result.error) continue

                const [logIdx] = this.parseLogIndex(field.name)
                const logNamePrefix = this.state.logs.length > 1 ? `L${logIdx}: ` : ''

                data.push({
                    x: result.x,
                    y: result.y,
                    name: logNamePrefix + field.name,
                    yaxis: field.axis === 0 ? 'y' : 'y' + (field.axis + 1),
                    line: { color: field.color }
                })

                const axisKey = field.axis === 0 ? 'yaxis' : 'yaxis' + (field.axis + 1)
                layout[axisKey].title = this.getAxisTitle(field.axis)
            }

            Plotly.newPlot(this.gd, data, layout, { responsive: true, displaylogo: false })
            this.gd.on('plotly_relayout', this.onRangeChanged)
            this.state.plotLoading = false
        }
    },
    computed: {
        chart () {
            return this.state.charts[this.chartIndex]
        }
    }
}
</script>
