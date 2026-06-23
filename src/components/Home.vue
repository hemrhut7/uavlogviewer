<template>
    <div id='vuewrapper' style="height: 100%;">
        <template v-if="state.mapLoading || state.plotLoading">
            <div id="waiting">
                <atom-spinner
                    :animation-duration="1000"
                    :color="'#64e9ff'"
                    :size="300"
                />
            </div>
        </template>
        <TxInputs fixed-aspect-ratio v-if="state.mapAvailable && state.showMap && state.showRadio"></TxInputs>
        <ParamViewer    @close="state.showParams = false" v-if="state.showParams && state.params"></ParamViewer>
        <MessageViewer
            @close="state.showMessages = false"
            v-if="state.showMessages && state.textMessages && state.textMessages.length > 0"
        ></MessageViewer>
        <DeviceIDViewer @close="state.showDeviceIDs = false" v-if="state.showDeviceIDs"></DeviceIDViewer>
        <AttitudeViewer
            @close="state.showAttitude = false"
            v-if="state.showAttitude && (state.timeAttitude.length > 0 || state.timeAttitudeQ.length > 0)"
        ></AttitudeViewer>
        <MagFitTool     @close="state.showMagfit = false" v-if="state.showMagfit"></MagFitTool>
        <EkfHelperTool  @close="state.showEkfHelper = false" v-if="state.showEkfHelper"></EkfHelperTool>
        <div class="container-fluid" style="height: 100%; overflow: hidden;">

            <sidebar/>

            <main class="col-md-9 ml-sm-auto col-lg-10 flex-column d-sm-flex" role="main">

                <div class="row"
                     v-bind:class="[state.showMap ? 'h-50' : 'h-100']"
                     v-if="state.plotOn"
                     style="overflow-y: auto; display: block;">
                    <div class="col-12" v-for="(chart, index) in state.charts" :key="'chart' + index">
                        <Plotly :chartIndex="index"/>
                    </div>
                </div>
                <div class="row" v-bind:class="[state.plotOn ? 'h-50' : 'h-100']"
                     v-if="state.mapAvailable && mapOk && state.showMap">
                    <div class="col-12 noPadding">
                        <CesiumViewer ref="cesiumViewer"/>
                    </div>
                </div>
            </main>

        </div>
    </div>
</template>

<script>
import isOnline from 'is-online'
import Plotly from '@/components/Plotly.vue'
import CesiumViewer from '@/components/CesiumViewer.vue'
import Sidebar from '@/components/Sidebar.vue'
import TxInputs from '@/components/widgets/TxInputs.vue'
import ParamViewer from '@/components/widgets/ParamViewer.vue'
import MessageViewer from '@/components/widgets/MessageViewer.vue'
import DeviceIDViewer from '@/components/widgets/DeviceIDViewer.vue'
import AttitudeViewer from '@/components/widgets/AttitudeWidget.vue'
import { store } from '@/components/Globals.js'
import { AtomSpinner } from 'epic-spinners'
import { Color } from 'cesium'
import colormap from 'colormap'
import { DataflashDataExtractor } from '../tools/dataflashDataExtractor'
import { MavlinkDataExtractor } from '../tools/mavlinkDataExtractor'
import { DjiDataExtractor } from '../tools/djiDataExtractor'
import MagFitTool from '@/components/widgets/MagFitTool.vue'
import EkfHelperTool from '@/components/widgets/EkfHelperTool.vue'
import Vue from 'vue'

export default {
    name: 'Home',
    created () {
        this.$eventHub.$on('messagesDoneLoading', this.extractFlightData)
        this.state.messages = {}
        this.state.timeAttitude = []
        this.state.timeAttitudeQ = []
        this.state.currentTrajectory = []
        isOnline().then(a => { this.state.isOnline = a })
        this.$eventHub.$on('cesium-time-changed', this.onCesiumTimeChanged)
    },
    beforeDestroy () {
        this.$eventHub.$off('messagesDoneLoading', this.extractFlightData)
        this.$eventHub.$off('cesium-time-changed', this.onCesiumTimeChanged)
    },
    data () {
        return {
            state: store,
            dataExtractor: null
        }
    },
    methods: {
        onCesiumTimeChanged (time) {
            if (this.state.params) {
                this.state.params.seek(time)
            }
        },
        extractFlightData () {
            let extractor
            if (this.state.logType === 'tlog') {
                extractor = MavlinkDataExtractor
            } else if (this.state.logType === 'dji') {
                extractor = DjiDataExtractor
            } else {
                extractor = DataflashDataExtractor
            }

            if ('FMTU' in this.state.messages && this.state.messages.FMTU.length === 0) {
                this.state.processStatus = 'ERROR PARSING?'
            }

            this.state.flightModeChanges = extractor.extractFlightModes(this.state.messages)
            Vue.delete(this.state.messages, 'MODE')

            this.state.events = extractor.extractEvents(this.state.messages)
            Vue.delete(this.state.messages, 'STAT')
            Vue.delete(this.state.messages, 'EV')

            this.state.mission = extractor.extractMission(this.state.messages)
            Vue.delete(this.state.messages, 'CMD')

            this.state.vehicle = extractor.extractVehicleType(this.state.messages)
            this.state.params = extractor.extractParams(this.state.messages)
            if (this.state.params !== undefined) {
                this.state.defaultParams = extractor.extractDefaultParams(this.state.messages)
            }

            if (this.state.vehicle === 'quadcopter') {
                if (this.state.params?.get('FRAME_TYPE') === 0) {
                    this.state.vehicle += '+'
                } else {
                    this.state.vehicle += 'x'
                }
            }
            this.state.textMessages = extractor.extractTextMessages(this.state.messages)
            Vue.delete(this.state.messages, 'MSG')

            if (this.state.colors.length === 0) {
                this.generateColorMMap()
            }
            this.state.attitudeSources = extractor.extractAttitudeSources(this.state.messages)
            if (this.state.attitudeSources.quaternions.length > 0) {
                const source = this.state.attitudeSources.quaternions[0]
                this.state.attitudeSource = source
                this.state.timeAttitudeQ = extractor.extractAttitudeQ(this.state.messages, source)
            } else if (this.state.attitudeSources.eulers.length > 0) {
                const source = this.state.attitudeSources.eulers[0]
                this.state.attitudeSource = source
                this.state.timeAttitude = extractor.extractAttitude(this.state.messages, source)
            }

            const attitudeData = this.state.timeAttitude || this.state.timeAttitudeQ
            if (attitudeData) {
                const list = Object.keys(attitudeData)
                this.state.lastTime = parseInt(list[list.length - 1])
            }

            this.state.trajectorySources = extractor.extractTrajectorySources(this.state.messages)
            if (this.state.trajectorySources.length > 0) {
                const first = this.state.trajectorySources[0]
                this.state.trajectorySource = first
                this.state.trajectories = extractor.extractTrajectory(
                    this.state.messages,
                    first
                )
                try {
                    this.state.currentTrajectory = this.state.trajectories[first].trajectory
                    this.state.timeTrajectory = this.state.trajectories[first].timeTrajectory
                } catch {
                    console.log('unable to load trajectory')
                }
            }
            try {
                if (this.state.messages?.GPS?.time_boot_ms) {
                    this.state.metadata = { startTime: extractor.extractStartTime(this.state.messages.GPS) }
                } else if (this.state.messages['GPS[0]']) {
                    this.state.metadata = {
                        startTime: extractor.extractStartTime(this.state.messages['GPS[0]'])
                    }
                }
            } catch (error) {
                console.log('unable to load metadata')
                console.log(error)
            }
            try {
                this.state.namedFloats = extractor.extractNamedValueFloatNames(this.state.messages)
            } catch (error) {
                console.log('unable to load named floats')
                console.log(error)
            }

            this.state.fences = extractor.extractFences(this.state.messages)

            this.state.processStatus = 'Processed!'
            this.state.processDone = true

            // Change to plot view after 2 seconds so the Processed status is readable
            setTimeout(() => { this.$eventHub.$emit('set-selected', 'plot') }, 2000)

            // Only set showMap to true if it is available and was previously unavailable
            if (!this.state.mapAvailable) {
                this.state.mapAvailable = (this.state.currentTrajectory && this.state.currentTrajectory.length > 0)
                if (this.state.mapAvailable) {
                    this.state.showMap = true
                }
            }
        },

        generateColorMMap () {
            const colorMapOptions = {
                colormap: 'hsv',
                nshades: Math.max(11, this.setOfModes.length),
                format: 'rgbaString',
                alpha: 1
            }
            // colormap used on legend.
            this.state.cssColors = colormap(colorMapOptions)

            // colormap used on Cesium
            colorMapOptions.format = 'float'
            this.state.colors = []
            for (const rgba of colormap(colorMapOptions)) {
                this.state.colors.push(new Color(rgba[0], rgba[1], rgba[2]))
            }
        }
    },
    components: {
        Sidebar,
        Plotly,
        CesiumViewer,
        AtomSpinner,
        TxInputs,
        ParamViewer,
        MessageViewer,
        DeviceIDViewer,
        AttitudeViewer,
        MagFitTool,
        EkfHelperTool
    },
    computed: {
        mapOk () {
            return (this.state.currentTrajectory !== undefined &&
                    this.state.currentTrajectory.length > 0)
        },
        setOfModes () {
            const set = []
            if (this.state.flightModeChanges) {
                for (const mode of this.state.flightModeChanges) {
                    if (!set.includes(mode[1])) {
                        set.push(mode[1])
                    }
                }
            }
            return set
        }
    }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>

    .nav-side-menu ul :not(collapsed) .arrow:before,
    .nav-side-menu li :not(collapsed) .arrow:before {
        font-family: 'Montserrat', sans-serif;
        content: "\f078";
        display: inline-block;
        padding-left: 10px;
        padding-right: 10px;
        vertical-align: middle;
        float: right;
    }

    body {
        margin: 0;
        padding: 0;
    }

    .container-fluid {
        padding-left: 0;
        padding-right: 0;
    }

    div .col-12 {
        padding-left: 0;
        padding-right: 0;
    }

    i {
        margin: 10px;
    }

    i .dropdown {
        float: right;
    }

    .noPadding {
        padding-left: 4px;
        padding-right: 6px;
        max-height: 100%;
    }

    div #waiting {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 1000;
        display: block;
        background-color: black;
        opacity: 0.75;
        text-align: center;
    }
    /* ATOM SPINNER */

      div .atom-spinner {
        margin: auto;
        margin-top: 15%;
    }

</style>
<style>
a {
    color: #ffffff !important;
}
</style>
