<template>
    <div>
        <li v-if="!sampleLoaded">
            <a @click="onLoadSample('sample')" class="section"><i class="fas fa-play"></i>  Open Sample </a>
        </li>
        <li v-if="url">
            <a @click="share" class="section"><i class="fas fa-share-alt"></i> {{ shared ? 'Copied to clipboard!' :
                'Share link'}}</a>
        </li>
        <li v-if="url">
            <a :href="'/uploaded/' + url" class="section" target="_blank"><i class="fas fa-download"></i> Download</a>
        </li>
        <div @click="browse" @dragover.prevent @drop="onDrop" id="drop_zone"
        v-if="uploadpercentage===-1">
            <p>Drop *.tlog or *.bin files here or click to browse</p>
            <input @change="onChange" id="choosefile" style="opacity: 0;" type="file" multiple>
        </div>
        <!--<b-form-checkbox @change="uploadFile()" class="uploadCheckbox" v-if="file!=null && !uploadStarted"> Upload
        </b-form-checkbox>-->
        <VProgress v-bind:complete="transferMessage"
                   v-bind:percent="uploadpercentage"
                   v-if="uploadpercentage > -1">
        </VProgress>
        <VProgress v-bind:complete="state.processStatus"
                   v-bind:percent="state.processPercentage"
                   v-if="state.processPercentage > -1"
        ></VProgress>
    </div>
</template>
<script>
import VProgress from './SideBarFileManagerProgressBar.vue'
import Worker from '../tools/parsers/parser.worker.js'
import { store } from './Globals'

import { MAVLink20Processor as MAVLink } from '../libs/mavlink'

// The global worker is removed in favor of per-log workers stored in this.state.logs

export default {
    name: 'Dropzone',
    data: function () {
        return {
            // eslint-disable-next-line no-undef
            mavlinkParser: new MAVLink(),
            uploadpercentage: -1,
            sampleLoaded: false,
            shared: false,
            url: null,
            transferMessage: '',
            state: store,
            file: null,
            uploadStarted: false
        }
    },
    created () {
        this.$eventHub.$on('loadType', this.loadType)
        this.$eventHub.$on('trimFile', this.trimFile)
    },
    beforeDestroy () {
        this.$eventHub.$off('open-sample')
    },
    methods: {
        trimFile () {
            if (this.state.worker) {
                this.state.worker.postMessage({ action: 'trimFile', time: this.state.timeRange })
            }
        },
        onLoadSample (file) {
            let url
            let filename
            let logType
            if (file === 'sample') {
                filename = 'sample'
                url = require('../assets/vtol.tlog').default
                logType = 'tlog'
            } else {
                url = file
                // Set the file name for display purposes
                const urlParts = url.split('/')
                filename = urlParts[urlParts.length - 1]
                logType = url.indexOf('.tlog') > 0 ? 'tlog' : 'bin'
                if (url.indexOf('.txt') > 0) {
                    logType = 'dji'
                }
            }

            this.state.filename = filename
            this.state.processStatus = 'Downloading...'
            this.state.processPercentage = 0
            this.state.messages = {}
            this.state.messageTypes = {}
            this.state.metadata = null
            this.state.logType = logType

            const oReq = new XMLHttpRequest()
            console.log(`loading file from ${url}`)

            oReq.open('GET', url, true)
            oReq.responseType = 'arraybuffer'

            const logWorker = new Worker()
            this.state.worker = logWorker
            logWorker.onmessage = (event) => {
                if (event.data.percentage) {
                    this.state.processPercentage = event.data.percentage
                } else if (event.data.availableMessages) {
                    this.state.messageTypes = event.data.availableMessages
                    this.$eventHub.$emit('messageTypes', event.data.availableMessages)
                } else if (event.data.metadata) {
                    this.state.metadata = event.data.metadata
                } else if (event.data.messages) {
                    this.state.messages = event.data.messages
                    this.$eventHub.$emit('messages')
                } else if (event.data.messagesDoneLoading) {
                    this.$eventHub.$emit('messagesDoneLoading')
                } else if (event.data.messageType) {
                    this.$set(this.state.messages, event.data.messageType, event.data.messageList)
                    this.$eventHub.$emit('messages')
                } else if (event.data.files) {
                    this.state.files = event.data.files
                    this.$eventHub.$emit('messages')
                } else if (event.data.url) {
                    this.downloadFileFromURL(event.data.url)
                }
            }

            oReq.onload = (oEvent) => {
                const arrayBuffer = oReq.response
                this.transferMessage = 'Download Done'
                this.sampleLoaded = true
                logWorker.postMessage({
                    action: 'parse',
                    file: arrayBuffer,
                    isTlog: (url.indexOf('.tlog') > 0),
                    isDji: (url.indexOf('.txt') > 0)
                })
            }
            oReq.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    this.uploadpercentage = 100 * e.loaded / e.total
                    this.state.processPercentage = this.uploadpercentage
                    this.state.processStatus = 'Downloading...'
                }
            }
            , false)
            oReq.onerror = (error) => {
                alert('unable to fetch remote file, check CORS settings in the target server')
                console.log(error)
            }

            oReq.send()
        },
        onChange (ev) {
            const fileinput = document.getElementById('choosefile')
            for (let i = 0; i < fileinput.files.length; i++) {
                this.process(fileinput.files[i])
            }
        },
        onDrop (ev) {
            // Prevent default behavior (Prevent file from being opened)
            ev.preventDefault()
            if (ev.dataTransfer.items) {
                // Use DataTransferItemList interface to access the file(s)
                for (let i = 0; i < ev.dataTransfer.items.length; i++) {
                    // If dropped items aren't files, reject them
                    if (ev.dataTransfer.items[i].kind === 'file') {
                        const file = ev.dataTransfer.items[i].getAsFile()
                        this.process(file)
                    }
                }
            } else {
                // Use DataTransfer interface to access the file(s)
                for (let i = 0; i < ev.dataTransfer.files.length; i++) {
                    this.process(ev.dataTransfer.files[i])
                }
            }
        },
        loadType: function (type) {
            if (this.state.worker) {
                this.state.worker.postMessage({
                    action: 'loadType',
                    type: type
                })
            }
        },
        process: function (file) {
            this.state.filename = file.name
            this.state.processStatus = 'Pre-processing...'
            this.state.processPercentage = 100
            this.state.messages = {}
            this.state.messageTypes = {}
            this.state.metadata = null
            this.state.logType = file.name.endsWith('tlog') ? 'tlog' : 'bin'
            if (file.name.endsWith('.txt')) {
                this.state.logType = 'dji'
            }

            const logWorker = new Worker()
            this.state.worker = logWorker
            logWorker.onmessage = (event) => {
                if (event.data.percentage) {
                    this.state.processPercentage = event.data.percentage
                } else if (event.data.availableMessages) {
                    this.state.messageTypes = event.data.availableMessages
                    this.$eventHub.$emit('messageTypes', event.data.availableMessages)
                } else if (event.data.metadata) {
                    this.state.metadata = event.data.metadata
                } else if (event.data.messages) {
                    this.state.messages = event.data.messages
                    this.$eventHub.$emit('messages')
                } else if (event.data.messagesDoneLoading) {
                    this.$eventHub.$emit('messagesDoneLoading')
                } else if (event.data.messageType) {
                    this.$set(this.state.messages, event.data.messageType, event.data.messageList)
                    this.$eventHub.$emit('messages')
                } else if (event.data.files) {
                    this.state.files = event.data.files
                    this.$eventHub.$emit('messages')
                } else if (event.data.url) {
                    this.downloadFileFromURL(event.data.url)
                }
            }

            const reader = new FileReader()
            reader.onload = function (e) {
                const data = reader.result
                logWorker.postMessage({
                    action: 'parse',
                    file: data,
                    isTlog: (file.name.endsWith('tlog')),
                    isDji: (file.name.endsWith('txt'))
                })
            }
            reader.readAsArrayBuffer(file)
        },
        uploadFile () {
            this.uploadStarted = true
            this.transferMessage = 'Upload Done!'
            this.uploadpercentage = 0
            const formData = new FormData()
            formData.append('file', this.file)

            const request = new XMLHttpRequest()
            request.onload = () => {
                if (request.status >= 200 && request.status < 400) {
                    this.uploadpercentage = 100
                    this.url = request.responseText
                } else {
                    alert('error! ' + request.status)
                    this.uploadpercentage = 100
                    this.transferMessage = 'Error Uploading'
                    console.log(request)
                }
            }
            request.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    this.uploadpercentage = 100 * e.loaded / e.total
                }
            }
            , false)
            request.open('POST', '/upload')
            request.send(formData)
        },
        fixData (message) {
            if (message.name === 'GLOBAL_POSITION_INT') {
                message.lat = message.lat / 10000000
                message.lon = message.lon / 10000000
                // eslint-disable-next-line
                message.relative_alt = message.relative_alt / 1000
            }
            return message
        },
        browse () {
            document.getElementById('choosefile').click()
        },
        share () {
            const el = document.createElement('textarea')
            el.value = window.location.host + '/#/v/' + this.url
            document.body.appendChild(el)
            el.select()
            document.execCommand('copy')
            document.body.removeChild(el)
            this.shared = true
        },
        downloadFileFromURL (url) {
            const a = document.createElement('a')
            document.body.appendChild(a)
            a.style = 'display: none'
            a.href = url
            a.download = this.state.file + '-trimmed.' + this.state.logType
            a.click()
            document.body.removeChild(a)
            window.URL.revokeObjectURL(url)
        }
    },
    mounted () {
        window.addEventListener('message', (event) => {
            if (event.data.type === 'arrayBuffer') {
                this.state.filename = 'external_log'
                this.state.processStatus = 'Pre-processing...'
                this.state.processPercentage = 100
                this.state.messages = {}
                this.state.messageTypes = {}
                this.state.metadata = null
                this.state.logType = 'bin'

                const logWorker = new Worker()
                this.state.worker = logWorker
                logWorker.onmessage = (workerEvent) => {
                    if (workerEvent.data.percentage) {
                        this.state.processPercentage = workerEvent.data.percentage
                    } else if (workerEvent.data.availableMessages) {
                        this.state.messageTypes = workerEvent.data.availableMessages
                        this.$eventHub.$emit('messageTypes', workerEvent.data.availableMessages)
                    } else if (workerEvent.data.messages) {
                        this.state.messages = workerEvent.data.messages
                        this.$eventHub.$emit('messages')
                    } else if (workerEvent.data.messageType) {
                        this.$set(this.state.messages, workerEvent.data.messageType, workerEvent.data.messageList)
                        this.$eventHub.$emit('messages')
                    }
                }
                logWorker.postMessage({
                    action: 'parse',
                    file: event.data.data,
                    isTlog: false,
                    isDji: false
                })
            }
        })
        const url = document.location.search.split('?file=')[1]
        if (url) {
            this.onLoadSample(decodeURIComponent(url))
        }
    },
    components: {
        VProgress
    }
}
</script>
<style scoped>

    /* NAVBAR */

    #drop_zone {
        padding-top: 25px;
        padding-left: 10px;
        border: 2px dashed #434b52da;
        width: auto;
        height: 100px;
        margin: 20px;
        border-radius: 5px;
        cursor: default;
        background-color: rgba(0, 0, 0, 0);
    }

    #drop_zone:hover {
        background-color: #171e2450;
    }

    .uploadCheckbox {
        margin-left: 20px;
    }

</style>
