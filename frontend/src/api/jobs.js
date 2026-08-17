//THIS FILE SHOULD ONLY COMMUNICATE WITH THE BACKEND

import {API_BASE_URL} from "./api";

export async function getJobs() {
    const response = await fetch(`${API_BASE_URL}/jobs`);

    if(!response.ok){
        throw new Error("FAILED TO FETCH JOBS");
    }

    const data = await response.json();

    return data.jobs;
}