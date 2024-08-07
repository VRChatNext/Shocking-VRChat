Vue.component('FormField', {
    props: ['id', 'label', 'value'],
    delimiters: ["[[", "]]"],
    template: `
    <div class="form-field">
        <div style="display: flex">
          <label v-if="!isObject(value) && !isArray(value)" class="form-label">[[label]]:</label>
          <input style="flex: 1" class="form-input" type="text" v-if="!isObject(value) && !isArray(value)" :id="id" v-model="value" @input="updateValue"/>
        </div>
          
        <div v-if="isObject(value) || isArray(value)">
            <div>
                <label class="form-label">[[label]]:</label>
                <div style="float: right;cursor: pointer; font-size: 1rem; margin-top: 1rem;" v-if="isArray(value)" @click="addToArray">
                    <i class="fas fa-plus"></i>
                </div>
            </div>
            <div/>
            <div class="nested" v-for="(item, key) in value" :key="key">
            <FormField :id="key" :label="key" :value="item" @update:value="nestedUpdate(key, $event)"></FormField>
        </div>
     </div>
    </div>
`,
    methods: {
        updateValue(event) {
            this.$emit('update:value', this.isNumber(event.target.value) ? parseFloat(event.target.value) : event.target.value);
        },
        nestedUpdate(key, newValue) {
            this.$set(this.value, key, newValue);
            this.$emit('update:value', this.value);
        },
        addToArray() {
            let newValue = this.value.concat('');
            this.$emit('update:value', newValue);
        },
        isObject(val) {
            return val !== null && typeof val === 'object' && !Array.isArray(val);
        },
        isArray(val) {
            return Array.isArray(val);
        },
        isNumber(val) {
            return !isNaN(parseFloat(val)) && isFinite(val);
        }
    }
});