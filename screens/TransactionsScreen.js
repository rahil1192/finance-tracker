import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  StatusBar,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import CategoriesTab from '../components/transactions/CategoriesTab';
import MerchantsTab from '../components/transactions/MerchantsTab';
import MonthlyTab from '../components/transactions/MonthlyTab';
import DailyTab from '../components/transactions/DailyTab';

const { width } = Dimensions.get('window');
const TABS = ['CATEGORIES', 'MERCHANTS', 'DAILY', 'MONTHLY', 'RECURRING'];

export default function TransactionsScreen() {
  const navigation = useNavigation();
  const [activeTab, setActiveTab] = useState('CATEGORIES');
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const horizontalScrollRef = useRef(null);
  const tabScrollRef = useRef(null);
  
  const handleAddTransaction = () => {
    navigation.navigate('AddTransaction');
  };

  const handleTabPress = (tab, index) => {
    setActiveTab(tab);
    setActiveTabIndex(index);
    
    // Scroll to the selected tab content
    if (horizontalScrollRef.current) {
      horizontalScrollRef.current.scrollTo({ x: index * width, animated: true });
    }
    
    // Ensure the selected tab is visible in the tab bar
    if (tabScrollRef.current) {
      tabScrollRef.current.scrollTo({ 
        x: index * 120 - width / 2 + 60, 
        animated: true 
      });
    }
  };

  const handleScroll = (event) => {
    const scrollX = event.nativeEvent.contentOffset.x;
    const index = Math.round(scrollX / width);
    
    if (index !== activeTabIndex) {
      setActiveTabIndex(index);
      setActiveTab(TABS[index]);
      
      // Ensure the selected tab is visible in the tab bar
      if (tabScrollRef.current) {
        tabScrollRef.current.scrollTo({ 
          x: index * 120 - width / 2 + 60, 
          animated: true 
        });
      }
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0c4a6e" />
      
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity>
          <Ionicons name="menu" size={24} color="#0ea5e9" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Transactions</Text>
        <View style={styles.headerIcons}>
          <TouchableOpacity style={styles.iconButton}>
            <Ionicons name="download-outline" size={24} color="#0ea5e9" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconButton}>
            <Ionicons name="filter" size={24} color="#0ea5e9" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconButton}>
            <Ionicons name="search" size={24} color="#0ea5e9" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab Navigation */}
      <View style={styles.tabContainer}>
        <ScrollView 
          ref={tabScrollRef}
          horizontal 
          showsHorizontalScrollIndicator={false}
        >
          {TABS.map((tab, index) => (
            <TouchableOpacity
              key={tab}
              style={[
                styles.tab,
                activeTab === tab && styles.activeTab
              ]}
              onPress={() => handleTabPress(tab, index)}
            >
              <Text
                style={[
                  styles.tabText,
                  activeTab === tab && styles.activeTabText
                ]}
              >
                {tab}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Horizontally Swipeable Tab Content */}
      <ScrollView
        ref={horizontalScrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={handleScroll}
        style={styles.horizontalScroll}
      >
        {/* CATEGORIES Tab */}
        <View style={[styles.tabPage, { width }]}>
          <CategoriesTab />
        </View>
        
        {/* MERCHANTS Tab */}
        <View style={[styles.tabPage, { width }]}>
          <MerchantsTab />
        </View>
        
        {/* DAILY Tab */}
        <View style={[styles.tabPage, { width }]}>
          <DailyTab />
        </View>
        
        {/* MONTHLY Tab */}
        <View style={[styles.tabPage, { width }]}>
          <MonthlyTab />
        </View>
        
        {/* RECURRING Tab */}
        <View style={[styles.tabPage, { width }]}>
          <View style={styles.placeholderContainer}>
            <Text style={styles.placeholderText}>RECURRING tab content</Text>
          </View>
        </View>
      </ScrollView>

      {/* Floating Action Button */}
      <View style={styles.fabContainer}>
        <TouchableOpacity 
          style={styles.fab}
          onPress={() => handleAddTransaction()}
          onLongPress={() => {
            // Show a menu to select transaction type
            // This is just a placeholder - you might want to implement a proper menu
            Alert.alert(
              "Add Transaction",
              "Select transaction type",
              [
                { text: "Expense", onPress: () => handleAddTransaction('Expense') },
                { text: "Income", onPress: () => handleAddTransaction('Income') },
                { text: "Transfer", onPress: () => handleAddTransaction('Transfer') },
                { text: "Cancel", style: "cancel" }
              ]
            );
          }}
        >
          <Ionicons name="add" size={32} color="white" />
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#0c4a6e',
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: 'white',
  },
  headerIcons: {
    flexDirection: 'row',
  },
  iconButton: {
    marginLeft: 16,
  },
  tabContainer: {
    backgroundColor: '#0f172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  tab: {
    paddingVertical: 16,
    paddingHorizontal: 20,
    minWidth: 120, // Ensure tabs have a minimum width
    alignItems: 'center',
  },
  activeTab: {
    borderBottomWidth: 3,
    borderBottomColor: '#0ea5e9',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#94a3b8',
  },
  activeTabText: {
    color: '#0ea5e9',
  },
  horizontalScroll: {
    flex: 1,
  },
  tabPage: {
    flex: 1,
  },
  placeholderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  placeholderText: {
    fontSize: 18,
    color: '#94a3b8',
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#0ea5e9',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    zIndex: 10,
  },
});