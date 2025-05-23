import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import HomeScreen from './screens/HomeScreen';
import BillsScreen from './screens/BillsScreen';
import TransactionsScreen from './screens/TransactionsScreen';
import BudgetScreen from './screens/BudgetScreen';
import AccountsScreen from './screens/AccountsScreen';
import AddBillModal from './components/AddBillModal';
import AddTransactionModal from './components/AddTransactionModal';
import BudgetTypeScreen from './components/BudgetFlow/BudgetTypeScreen';
import BudgetDetailsScreen from './components/BudgetFlow/BudgetDetailsScreen';
import BudgetReviewScreen from './components/BudgetFlow/BudgetReviewScreen';
import { Ionicons } from '@expo/vector-icons';

const Tab = createBottomTabNavigator();
const Stack = createStackNavigator();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName;

          if (route.name === 'Home') {
            iconName = focused ? 'home' : 'home-outline';
          } else if (route.name === 'Bills') {
            iconName = focused ? 'document-text' : 'document-text-outline';
          } else if (route.name === 'Transactions') {
            iconName = focused ? 'list' : 'list-outline';
          } else if (route.name === 'Budget') {
            iconName = focused ? 'bar-chart' : 'bar-chart-outline';
          } else if (route.name === 'Accounts') {
            iconName = focused ? 'business' : 'business-outline';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: '#0284c7',
        tabBarInactiveTintColor: 'gray',
        headerShown: false,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="Bills" component={BillsScreen} />
      <Tab.Screen name="Transactions" component={TransactionsScreen} />
      <Tab.Screen name="Budget" component={BudgetScreen} />
      <Tab.Screen name="Accounts" component={AccountsScreen} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="auto" />
        <NavigationContainer>
          <Stack.Navigator mode="modal">
            <Stack.Screen 
              name="Main" 
              component={MainTabs} 
              options={{ headerShown: false }} 
            />
            <Stack.Screen 
              name="AddBill" 
              component={AddBillModal} 
              options={{ 
                headerShown: false,
                presentation: 'modal',
                cardStyle: { backgroundColor: 'white' }
              }} 
            />
            
            <Stack.Screen 
              name="AddTransaction" 
              component={AddTransactionModal} 
              options={{ 
                headerShown: false,
                presentation: 'modal',
                cardStyle: { backgroundColor: 'white' }
              }} 
            />
            <Stack.Screen 
              name="BudgetTypeSelection" 
              component={BudgetTypeScreen} 
              options={{ 
                headerShown: false,
                presentation: 'modal',
                cardStyle: { backgroundColor: 'white' }
              }} 
            />
            <Stack.Screen 
              name="BudgetDetailsScreen" 
              component={BudgetDetailsScreen} 
              options={{ 
                headerShown: false,
                cardStyle: { backgroundColor: 'white' }
              }} 
            />
            <Stack.Screen 
              name="BudgetReviewScreen" 
              component={BudgetReviewScreen} 
              options={{ 
                headerShown: false,
                cardStyle: { backgroundColor: 'white' }
              }} 
            />
          </Stack.Navigator>
        </NavigationContainer>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}