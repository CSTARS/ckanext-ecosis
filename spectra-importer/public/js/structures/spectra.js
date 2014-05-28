esis.structures.Spectra = function(spectra, filename, sheetname) {
	var data = [];
	var error = null;
	var ckanId = "";

	var joinOrder = ['joined', 'file', 'spectra'];
	var metadata = {
		spectra : {},
		file : {},
		joined : {}
	}

	if( spectra.data ) data = spectra.data;
	if( spectra.metadata ) metadata.spectra = spectra.metadata;

	function setData(data) {
		data = d;
	}

	function getData() {
		return data;
	}

	function setMetadata(type, key, value) {
		metadata[type][key] = value;
	}

	function getJoinedMetadata() {
		var md = {};
		for( var i = 0; i < joinOrder.length; i++ ) {
			for( var key in metadata[joinOrder[i]] ) {
				md[key] = metadata[joinOrder[i]][key];
			}
		}
		return md;
	}

	function getMetadata() {
		return metadata;
	}

	function getError() {
		return error;
	}

	function setError(e) {
		error = e;
	}

	function hasError() {
		if( error === null ) return false;
		return true;
	}

	function getFilename() {
		return filename;
	}

	function getSheetname() {
		if( sheetname ) return sheetname;
		return '';
	}

	function getCkanId() {
		return ckanId;
	}

	function setCkanId(id) {
		ckanId = id;
	}

	esis.structures.importer.updateInfo();

	return {
		setData : setData,
		getData : getData,
		setMetadata : setMetadata,
		getMetadata : getMetadata,
		getJoinedMetadata : getJoinedMetadata,
		getFilename : getFilename,
		getSheetname : getSheetname,
		getError : getError,
		setError : setError,
		hasError : hasError,
		getCkanId : getCkanId,
		setCkanId : setCkanId
	}
}