function() {
    var key = this.ecosis.package_id;

    if( this.ecosis.group_by && this.ecosis.group_by != '' ) {
        key += '-'+this[this.ecosis.group_by];
    }
    this.count = 1;

    emit(key, this);
}