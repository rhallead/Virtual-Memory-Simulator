#!/usr/bin/env python

import sys
import os
import struct
from collections import deque

# notes

# if we have a hard miss, we need to put it into memory
# if physical memory is full, use page replacement. take something out of physcial memory and put something in, update tlb and page table respectively
# regardless of soft miss or hard miss, you update tlb


# Global Variables
PAGE_SIZE = 256
TLB_SIZE = 16
PT_SIZE = 256
FRAME_SIZE = 256

# page table list 
pagetable = [None] * PT_SIZE
ptcount = 0

# tlb queue
tlb = []
tlbcount = 0

# physical memory
physical_memory = []
frames = 0

# page replacememnt algorithm
pra = None

# print variables
page_faults = 0
tlb_hits = 0
tlb_misses = 0

# for LRU
access_history = []
fifo_queue_mem = []

# for OPT
future_references = []

# Page Table Entry class
class PageTableEntry:
    def __init__(self, page_number, frame_number, valid=False):
        self.page_number = page_number
        self.frame_number = frame_number
        self.valid = valid

# Address class to keep track of each address and its info
class Address:
    def __init__(self, fulladdress):
        self.fulladd = fulladdress
        self.pagenumber = fulladdress // 256
        self.pageoffset = fulladdress % 256
        self.framenum = -1
        self.value = -1

# FIFO pra
def add_to_physicalmem_fifo(pagenumber):
    global frames

    if len(physical_memory) >= frames:
        oldpagenum = fifo_queue_mem.pop(0)
        frame = physical_memory.index(oldpagenum)
        physical_memory[frame] = pagenumber
        pagetable[oldpagenum] = PageTableEntry(oldpagenum, -1, False) # update old page number to false
        tlb_remove(oldpagenum)
    else:
        frame = len(physical_memory)
        physical_memory.append(pagenumber)

    fifo_queue_mem.append(pagenumber)

    return frame

# LRU pra
def add_to_physicalmem_lru(pagenumber):
    global frames, access_history, physical_memory, pagetable

    if len(physical_memory) >= frames:
        oldpagenum = access_history.pop(0) # remove least recently used address
        frame = physical_memory.index(oldpagenum)
        physical_memory[frame] = pagenumber
        pagetable[oldpagenum].valid = False
        #pagetable[oldpagenum] = PageTableEntry(oldpagenum, -1, False)
        tlb_remove(oldpagenum)
    else:
        frame = len(physical_memory)
        physical_memory.append(pagenumber)

    # access_history.append(pagenumber)

    return frame

# OPT pra
def add_to_physicalmem_opt(pagenumber, current_index):
    global frames, future_references, pagetable, physical_memory

    if len(physical_memory) >= frames:
        farthest_use = 0
        oldpagenum = physical_memory[0]
        oldpage_index = 0

        for i, page in enumerate(physical_memory):
            try:
                # next_use = future_references.index(page)
                next_use = future_references[current_index:].index(page)
            except ValueError:
                # If the page isn't found in future references, it will not be used again.
                next_use = len(future_references) #index will never reach here, so this is the biggest number

            if next_use > farthest_use:
                farthest_use = next_use
                oldpagenum = page
                oldpage_index = i

        frame = oldpage_index
        physical_memory[frame] = pagenumber
        pagetable[oldpagenum].valid = False
        tlb_remove(oldpagenum)
    else:
        frame = len(physical_memory)
        physical_memory.append(pagenumber)

    return frame

# LRU to keep track of recently used
def update_access_history(page_number):
    global access_history
    if page_number in access_history:
        access_history.remove(page_number)
    access_history.append(page_number)


# Add page number to tlb
def tlb_add(page_number, frame_number):
    if len(tlb) == TLB_SIZE:
        tlb.pop(0)
    tlb.append((page_number, frame_number))


# Look up a page number in the TLB and return the frame number if found
def tlb_lookup(page_number):
    global tlb_hits, tlb_misses
    for entry in tlb:
        if entry[0] == page_number:
            tlb_hits += 1  # Increment TLB hit counter
            #if pra == 'LRU': TODO
                # update LRU queue
            return entry[1]  # Return the frame number
    tlb_misses += 1  # Increment TLB miss counter
    return None

# Remove a page number from tlb
def tlb_remove(page_number):
    for entry in tlb:
        if entry[0] == page_number:
            tlb.remove(entry)

# Look up a page number in page table and return frame number if valid
def page_table_lookup(pagenumber):
    global page_faults
    entry = pagetable[pagenumber]

    if entry is not None:
        if entry.valid:
            return entry.frame_number
    
    page_faults += 1
    return None


# Load a page from the backing store into physical memory
def load_page_from_backing_store(address):
    offset = address.pageoffset
    # open backing store
    with open('BACKING_STORE.bin', 'rb') as f:
        f.seek(address.pagenumber * 256)
        data = f.read(FRAME_SIZE)
        # get value bit and make sure it is signed
        address.value = int.from_bytes(data[offset:offset + 1], byteorder="big", signed=True)
        hexdata = data.hex()
    f.close()
    return hexdata


# Access a memory address and handle TLB and page table lookups and faults
def access_memory(address, current_index):
    global pagetable, pra, tlb_hits
    hexdata = load_page_from_backing_store(address)

    pagenumber = address.pagenumber

    frame_number = tlb_lookup(pagenumber)  # Look up in TLB

    if frame_number is None: # if misses tlb (soft miss)
        frame_number = page_table_lookup(pagenumber)  # Look up in page table

        if frame_number is None: # if its not in page table (hard miss) or not valid
            # add to physical memory 
            if pra == 'LRU':
                frame_number = add_to_physicalmem_lru(pagenumber)
            elif pra == 'OPT':
                frame_number = add_to_physicalmem_opt(pagenumber, current_index)
            else: # FIFO
                frame_number = add_to_physicalmem_fifo(pagenumber)

            # add to or edit pagetable
            pagetable[pagenumber] = PageTableEntry(pagenumber, frame_number, True)

        tlb_add(pagenumber, frame_number)  # add to TLB

    address.framenum = frame_number  # set frame number

    print(address.fulladd, ", ", address.value, ", ", address.framenum, ", ", hexdata)
    
    if pra == "LRU":
        update_access_history(pagenumber)


def main():
    global frames, physical_memory, pra, future_references
    # make sure right number of arguments is passed in
    if len(sys.argv) not in [4, 2]:
        print("Error: Wrong number of arguments")
        sys.exit(1)

    ref_file = sys.argv[1]
    frames = 256
    pra = "FIFO"

    # change frames and pra if given by user
    if len(sys.argv) == 4:
        try:
            frames = int(sys.argv[2])
        except ValueError:
            print('Error: FRAMES must be an integer between 0 and 256')
            sys.exit(1)
        pra = sys.argv[3]
        # check that pra is valid
        if pra not in ['FIFO', 'LRU', 'OPT']:
            print('Error: PRA must be  either FIFO, LRU, or OPT')
            sys.exit(1)

    #check if frames is withint 0 and 256
    if frames < 0 or frames > 256:
        print("Error: FRAMES must be an integer between 0 and 256")
        sys.exit()

    #read reference file and get every address
    with open(ref_file) as f:
        addresses = [int(line.strip()) for line in f]
    
    # for opt use only, makes list of pagenums from addresses
    future_references = [x // 256 for x in addresses]

    # go through every address
    for i, fulladd in enumerate(addresses):
        address = Address(fulladd)  # Create Address object
        access_memory(address, i)

    
    output = (
        f"Number of Translated Addresses = {len(addresses)}\n"
        f"Page Faults = {page_faults}\n"
        f"Page Fault Rate = {page_faults/len(addresses):.3f}\n"
        f"TLB Hits = {tlb_hits}\n"
        f"TLB Misses = {tlb_misses}\n"
        f"TLB Hit Rate = {tlb_hits/len(addresses):.3f}"
    )

    print(output)

    return 0

if __name__ == "__main__":
    main()